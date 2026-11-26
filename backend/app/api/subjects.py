"""Subjects: the user's courses. They group exams and Decks and may exist while empty."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..anki import BELOW, LIMIT, build_deck
from ..core import config
from ..db.exams import course_id
from ..db.models import Course, Exam, Integration, Job, User
from ..db.session import get_db
from ..mcp import tools
from .auth import current_user

router = APIRouter()


class SubjectOut(BaseModel):
    id: uuid.UUID
    name: str


class SubjectIn(BaseModel):
    name: str = Field(max_length=100)


def _name(body: SubjectIn) -> str:
    name = body.name.replace("\x00", "").strip()
    if not name:
        raise HTTPException(422, detail={"code": "empty_name"})
    return name


@router.get("/subjects")
def list_subjects(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[SubjectOut]:
    """Every subject of the user, empty ones and ones only exams use included."""
    rows = db.scalars(select(Course).where(Course.user_id == user.id).order_by(func.lower(Course.name)))
    return [SubjectOut(id=c.id, name=c.name) for c in rows]


@router.post("/subjects")
def create_subject(body: SubjectIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> SubjectOut:
    """Names are unique ignoring case, so an existing one is returned as it is."""
    name = _name(body)
    cid = course_id(db, user.id, name)
    db.commit()
    return SubjectOut(id=cid, name=db.scalar(select(Course.name).where(Course.id == cid)))


@router.get("/subjects/{subject_id}/anki")
def download_anki(
    subject_id: uuid.UUID, below: float = Query(BELOW, ge=0, le=1), db: Session = Depends(get_db), user: User = Depends(current_user)
) -> Response:
    """The subject's weak subtasks (latest score share below `below`) as an Anki deck."""
    course = db.get(Course, subject_id)
    if course is None or course.user_id != user.id:
        raise HTTPException(404)
    deck = build_deck(db, user.id, course, below)
    if deck is None:
        raise HTTPException(409, detail={"code": "nothing_weak"})
    return Response(deck, media_type="application/octet-stream", headers={"Content-Disposition": 'attachment; filename="exam-sim.apkg"'})


@router.post("/subjects/{subject_id}/notion", status_code=202)
def queue_notion_export(subject_id: uuid.UUID, response: Response, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Queues the subject's weak subtasks for export to Notion; follow GET /jobs/{id}/events. An active job is returned as it is."""
    course = db.get(Course, subject_id)
    if not config.NOTION_ENABLED or course is None or course.user_id != user.id:
        raise HTTPException(404)
    if not db.scalar(select(Integration.id).where(Integration.user_id == user.id, Integration.provider == "notion")):
        raise HTTPException(409, detail={"code": "notion_not_connected"})
    if not tools.weak_refs(db, user.id, course.id, BELOW, LIMIT):
        raise HTTPException(409, detail={"code": "nothing_weak"})
    active = select(Job.id).where(Job.course_id == course.id, Job.kind == "notion", Job.status.in_(("queued", "running")))
    job_id = db.scalar(active)
    if job_id is None:
        job_id = uuid.uuid4()
        db.add(Job(id=job_id, kind="notion", filename="notion", subject=course.name, course_id=course.id, user_id=user.id))
        try:
            db.commit()
        except IntegrityError:  # a second click or tab won the race: the unique index allows one active job
            db.rollback()
            job_id = db.scalar(active)
            if job_id is None:  # the winner already finished, or the conflict was something else
                raise
    response.headers["Location"] = f"/api/jobs/{job_id}"
    return {"jobId": job_id}


@router.patch("/subjects/{subject_id}")
def rename_subject(subject_id: uuid.UUID, body: SubjectIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> SubjectOut:
    course = db.get(Course, subject_id)
    if course is None or course.user_id != user.id:  # a foreign id looks like a missing one
        raise HTTPException(404)
    name = _name(body)
    taken = db.scalar(select(Course.id).where(Course.user_id == user.id, func.lower(Course.name) == name.lower(), Course.id != course.id))
    if taken:
        raise HTTPException(409, detail={"code": "name_taken"})
    course.name = name
    # exams carry the name on the client; a newer edit time makes every device take the new one on its next pull
    db.execute(update(Exam).where(Exam.course_id == course.id).values(edited_at=func.now()))
    try:
        db.commit()
    except IntegrityError:  # lost a race with another request using the same name
        db.rollback()
        raise HTTPException(409, detail={"code": "name_taken"})
    return SubjectOut(id=course.id, name=name)
