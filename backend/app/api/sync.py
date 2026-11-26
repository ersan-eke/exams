import base64
import binascii
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from sqlalchemy import func, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..core.storage import CROP_NAME, exam_dir
from ..db.attempts import read_attempt, subtask_keys, write_attempt
from ..db.exams import course_id, to_rows
from ..db.models import Attempt, Course, Exam, Subtask, Task, User
from ..db.session import get_db
from ..db.sync import AttemptWire, ExamPut, SyncOut, dt, exam_meta
from .auth import current_user
from .routes import read_capped

router = APIRouter()

MAX_SYNC_BYTES = 50_000_000
SYNC_PAGE = 50  # attempts per response: each carries its pen strokes
SYNC_OVERLAP = timedelta(seconds=10)  # covers commit-order skew between the cursor read and concurrent writes
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _decode_crops(images: dict[str, str]) -> dict[str, bytes]:
    """Names become file names, so only plain ones pass; every file must really be a PNG."""
    out = {}
    for name, data in images.items():
        try:
            raw = base64.b64decode(data, validate=True)
        except binascii.Error:
            raw = b""
        if not CROP_NAME.fullmatch(name) or not raw.startswith(PNG_SIGNATURE):
            raise HTTPException(422, detail=f"bad crop {name!r}")
        out[name] = raw
    return out


def _write_crops(crops_dir, crops: dict[str, bytes]) -> None:
    crops_dir.mkdir(parents=True, exist_ok=True)
    for name, raw in crops.items():
        (crops_dir / name).write_bytes(raw)


async def _end_auth_transaction(db: Session) -> None:
    """The auth query opened a transaction: end it before the upload (which can be slow), so no connection is held meanwhile
    and now() is the write's time, not the upload's start."""
    await run_in_threadpool(db.rollback)


def _once_more_on_conflict(put, db: Session, *args) -> None:
    """Two first PUTs of one id can both miss the row and insert; the loser retries as an update.

    shortcut: one retry, so three or more simultaneous first PUTs can still 500; loop a few times if that is ever seen."""
    try:
        put(db, *args)
    except IntegrityError:
        db.rollback()
        put(db, *args)


def _put_exam(db: Session, user: User, exam_id: uuid.UUID, body: ExamPut) -> None:
    exam = db.get(Exam, exam_id)
    if exam is not None and exam.user_id not in (None, user.id):
        raise HTTPException(404)
    subject = None if body.subject is None else body.subject.replace("\x00", "")[:100].strip()
    cols = dict(
        title=body.title,
        hidden=body.hidden,
        point_overrides=body.point_overrides,
        rubrics={k: [line.model_dump() for line in v] for k, v in body.rubrics.items()} if body.rubrics else None,
        solution_for=body.solution_for,
        fingerprint=body.fingerprint,
        edited_at=dt(body.edited_at),
    )
    if exam is not None:
        exam.user_id = user.id  # claims an anonymous upload, even when the edit below is stale
        if exam.edited_at > dt(body.edited_at):  # rows the worker made have epoch 0, so a first push applies
            db.commit()
            return
        if subject is not None:  # null/absent keeps the worker's course, "" clears it
            cols["course_id"] = course_id(db, user.id, subject) if subject else None
        for k, v in cols.items():
            setattr(exam, k, v)
        db.commit()
        return
    if body.structure is None or body.images is None or (body.has_ink and body.solution_images is None):
        raise HTTPException(409, detail={"code": "need_content"})
    blank = _decode_crops(body.images or {})
    ink = _decode_crops(body.solution_images or {})
    _write_crops(exam_dir(exam_id) / "blank" / "crops", blank)
    if body.has_ink:
        _write_crops(exam_dir(exam_id) / "ink" / "crops", ink)
    cols["course_id"] = course_id(db, user.id, subject) if subject else None
    # shortcut: orphan crops on failed commits, clean up when storage moves to object storage
    # shortcut: the same PDF uploaded on two devices before they sync becomes two exams; merge by fingerprint and remap attempts when it bites
    db.add(to_rows(exam_id, body.structure, user_id=user.id, has_ink=body.has_ink, created_at=dt(body.created_at), **cols))
    db.commit()


@router.put("/exams/{exam_id}", status_code=204)
async def put_exam(
    exam_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    await _end_auth_transaction(db)
    raw = await read_capped(request, MAX_SYNC_BYTES)
    try:
        body = ExamPut.model_validate_json(raw)
    except ValidationError as e:
        raise HTTPException(422, detail=e.errors(include_url=False, include_context=False, include_input=False))
    if body.id != exam_id:
        raise HTTPException(422, detail="id mismatch")
    await run_in_threadpool(_once_more_on_conflict, _put_exam, db, user, exam_id, body)


def _put_attempt(db: Session, user: User, attempt_id: uuid.UUID, body: AttemptWire) -> None:
    row = db.get(Attempt, attempt_id)
    if row is not None and row.user_id != user.id:
        raise HTTPException(404)
    for exam_id in (body.exam_id, body.solution_exam_id):
        exam = exam_id and db.get(Exam, exam_id)
        if exam_id and (exam is None or exam.user_id != user.id):
            raise HTTPException(409, detail={"code": "need_exam"})
    if row is not None and row.edited_at > dt(body.edited_at):
        return
    try:
        write_attempt(db, user.id, body, subtask_keys(db, body.exam_id))
    except ValueError as e:
        db.rollback()
        raise HTTPException(422, detail=str(e))
    db.commit()


@router.put("/attempts/{attempt_id}", status_code=204)
async def put_attempt(
    attempt_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    await _end_auth_transaction(db)
    raw = await read_capped(request, MAX_SYNC_BYTES)
    try:
        body = AttemptWire.model_validate_json(raw)
    except ValidationError as e:
        raise HTTPException(422, detail=e.errors(include_url=False, include_context=False, include_input=False))
    if body.id != attempt_id:
        raise HTTPException(422, detail="id mismatch")
    await run_in_threadpool(_once_more_on_conflict, _put_attempt, db, user, attempt_id, body)


@router.get("/sync", response_model=SyncOut, response_model_by_alias=True)
def get_sync(
    since: datetime | None = None,
    after: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Exams and attempts changed since the cursor. Attempts come SYNC_PAGE at a time ordered by (updated_at, id); while `more`,
    ask again with `since=page_since&after=after` (exams only on the first page, no overlap on later ones)."""
    if after is not None and since is None:
        raise HTTPException(422, detail="after needs since")
    cursor = db.scalar(select(func.now()))
    exams = select(Exam, Course.name).outerjoin(Course).where(Exam.user_id == user.id)
    attempts = select(Attempt).where(Attempt.user_id == user.id).options(
        selectinload(Attempt.answers), selectinload(Attempt.times), selectinload(Attempt.grades)
    )  # fmt: skip
    if since is not None and after is None:
        try:
            since -= SYNC_OVERLAP
        except OverflowError:  # a cursor before the dawn of time is a full pull
            since = None
    if since is not None:
        exams = exams.where(Exam.updated_at > since)
        if after is None:
            attempts = attempts.where(Attempt.updated_at > since)
        else:
            attempts = attempts.where(tuple_(Attempt.updated_at, Attempt.id) > (since, after))
    rows = db.scalars(attempts.order_by(Attempt.updated_at, Attempt.id).limit(SYNC_PAGE + 1)).all()
    more = len(rows) > SYNC_PAGE
    rows = rows[:SYNC_PAGE]
    keys: dict[int, str] = {}
    ids = {r.exam_id for r in rows}
    for i, k in db.execute(select(Subtask.id, Subtask.key).join(Task).where(Task.exam_id.in_(ids))):
        keys[i] = k
    return SyncOut(
        cursor=cursor.isoformat(),
        more=more,
        after=rows[-1].id if more else None,
        page_since=rows[-1].updated_at.isoformat() if more else None,
        exams=[] if after is not None else [exam_meta(e, subject) for e, subject in db.execute(exams)],
        attempts=[read_attempt(r, keys) for r in rows],
    )
