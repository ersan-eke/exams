import asyncio
import base64
import time
import uuid
from collections.abc import AsyncIterable
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.sse import EventSourceResponse
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.orm import Session, selectinload

from ..core.storage import exam_dir, save_capped, upload_path
from ..core.text import clean
from ..db.exams import from_rows
from ..db.models import Exam, Job, Task, User
from ..db.session import SessionLocal, get_db
from ..grading.grader import grade_stream
from ..grading.limits import grade_limiter
from ..grading.models import GradeIn
from ..rag.material import material_for
from .auth import COOKIE, invited_user, optional_user, session_user

router = APIRouter()

JOB_EVENTS_DEADLINE = 15 * 60  # the worker's STALE time: a job that has not moved for this long is stuck
MAX_EXAM_BYTES = 50 * 1024 * 1024  # exams are a few MB; this only stops runaway anonymous uploads


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    status: Literal["queued", "running", "done", "failed"]
    stage: str | None
    error_code: str | None
    exam_id: uuid.UUID | None
    document_id: uuid.UUID | None


def _visible(owner: uuid.UUID | None, user: User | None) -> bool:
    """Anonymous uploads are reachable by whoever holds the (unguessable) id; account uploads only by their owner."""
    return owner is None or (user is not None and user.id == owner)


def _encode(crops_dir: Path) -> dict[str, str]:
    return {p.name: base64.b64encode(p.read_bytes()).decode() for p in sorted(crops_dir.glob("*.png"))}


@router.post("/exams", status_code=202)
def upload_exam(
    response: Response,
    file: UploadFile = File(...),
    role: Literal["exam", "solution"] = Form("exam"),
    subject: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User | None = Depends(invited_user),
):
    """Queues the PDF for the worker; follow GET /jobs/{job_id}/events until it is done."""
    if file.file.read(5) != b"%PDF-":
        raise HTTPException(400, detail={"code": "not_pdf"})
    file.file.seek(0)
    subject = clean(subject)  # client input
    job = Job(
        id=uuid.uuid4(),
        filename=clean(file.filename, 255) or "upload.pdf",
        role=role,
        user_id=user and user.id,
        subject=subject if user and role == "exam" else None,
    )
    path = upload_path(job.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_capped(file.file, path, MAX_EXAM_BYTES)  # before the commit, so the worker never sees a job without its file
    db.add(job)
    db.commit()
    response.headers["Location"] = f"/api/jobs/{job.id}"
    return {"job_id": job.id}


@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db), user: User | None = Depends(optional_user)) -> JobOut:
    job = db.get(Job, job_id)
    if job is None or not _visible(job.user_id, user):
        raise HTTPException(404)
    return JobOut.model_validate(job)


def _read_job(job_id: uuid.UUID) -> tuple[JobOut | None, datetime | None]:
    """The job and its lock time, which the worker bumps on every stage and every Notion card."""
    # own short session per read: the stream must not hold a DB connection while it waits
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        return (job and JobOut.model_validate(job)), job and job.locked_at


def _visible_job(job_id: uuid.UUID, request: Request) -> uuid.UUID:
    # a dependency runs before streaming starts, so an unknown id is a real 404 (EventSource then stops retrying);
    # own short session, since a get_db one would hold a pooled connection for the whole stream
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None or not _visible(job.user_id, session_user(db, request.cookies.get(COOKIE))):
            raise HTTPException(404)
    return job_id


@router.get("/jobs/{job_id}/events", response_class=EventSourceResponse)
async def job_events(job_id: uuid.UUID = Depends(_visible_job)) -> AsyncIterable[JobOut]:
    """Sends the job whenever it changes and ends after done/failed."""
    last, beat, deadline = None, None, time.monotonic() + JOB_EVENTS_DEADLINE
    while True:
        job, locked_at = await run_in_threadpool(_read_job, job_id)
        if job != last:
            yield job
        if job != last or locked_at != beat:  # a live job moves; as in the worker's claim(), only a silent one is stuck
            last, beat, deadline = job, locked_at, time.monotonic() + JOB_EVENTS_DEADLINE
        if job.status in ("done", "failed"):
            return
        if time.monotonic() > deadline:  # a plain end would make EventSource reconnect forever; "failed" makes the client stop
            yield job.model_copy(update={"status": "failed", "error_code": "server"})
            return
        await asyncio.sleep(1)  # shortcut: polls the row; LISTEN/NOTIFY once many clients watch at once


@router.get("/exams/{exam_id}")
def get_exam(exam_id: uuid.UUID, db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    exam = db.get(Exam, exam_id, options=[selectinload(Exam.tasks).selectinload(Task.subtasks)])
    if exam is None or not _visible(exam.user_id, user):
        raise HTTPException(404)
    d = exam_dir(exam_id)
    return {
        "exam": from_rows(exam).model_dump(mode="json"),
        "images": _encode(d / "blank" / "crops"),
        "solution_images": _encode(d / "ink" / "crops") if exam.has_ink else None,
    }


MAX_GRADE_BYTES = 25_000_000


def check_declared(request: Request, limit: int) -> None:
    """413 when the declared Content-Length is past `limit`, before the body is read."""
    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        raise HTTPException(400, detail="bad content-length") from None
    if declared > limit:
        raise HTTPException(413)


async def read_capped(request: Request, limit: int) -> bytes:
    """The body, or 413 past `limit`; the cap also holds for chunked bodies without Content-Length."""
    check_declared(request, limit)
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            raise HTTPException(413)
    return bytes(body)


async def _grade_request(request: Request) -> tuple[GradeIn, str]:
    """Checks run as a dependency so their HTTP errors land before the stream starts."""
    check_declared(request, MAX_GRADE_BYTES)  # an oversized request costs no limiter token
    key = request.headers.get("x-llm-key", "").strip()
    if not key:
        raise HTTPException(400, detail={"code": "no_key"})
    # behind the tunnel uvicorn runs with --proxy-headers and nginx sets X-Forwarded-For from CF-Connecting-IP,
    # so request.client.host is the real client address there (and the direct peer in local dev)
    if not grade_limiter.allow(request.client.host if request.client else "?"):
        raise HTTPException(429, detail={"code": "rate_limited"})
    body = await read_capped(request, MAX_GRADE_BYTES)
    try:
        return GradeIn.model_validate_json(body), key
    except ValidationError as e:
        raise HTTPException(422, detail=e.errors(include_url=False, include_context=False, include_input=False))


@router.post("/grade", response_class=EventSourceResponse, dependencies=[Depends(invited_user)])
async def grade(request: Request, args: tuple[GradeIn, str] = Depends(_grade_request)) -> AsyncIterable[dict]:
    """Grades one answer with the caller's own LLM key (header only, never stored or logged)."""
    req, key = args
    req.material = ""
    if req.subject and not req.solution:  # a solution sheet is the whole template: nothing else is added to the request
        req.material = await run_in_threadpool(material_for, request.cookies.get(COOKIE), req.subject, req.question.text, req.exclude_exams)
    async for event in grade_stream(req, key):
        yield event
