"""Study material: PDFs (slides chapters, scripts, tutorial exercises) filed under a subject, or unassigned until the user files them."""

import logging
import re
import shutil
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.storage import doc_dir, save_capped, upload_path
from ..core.text import clean
from ..db.exams import course_id
from ..db.models import Course, DeckPage, Document, Job, User
from ..db.session import get_db, read_then_release
from ..grading.grader import GradingError, complete
from ..grading.limits import ask_limiter
from ..grading.models import Provider, resolve_model
from ..rag import outline as rag_outline
from ..rag.deck import read_deck
from .auth import current_user

router = APIRouter()
log = logging.getLogger(__name__)

MAX_BYTES = 100 * 1024 * 1024  # slide decks are big; this only stops runaway uploads
Kind = Literal["slides", "script", "exercises"]


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    kind: Kind
    subject: str | None
    position: int
    page_count: int  # 0 while the worker is still reading it
    outline: list[dict] | None  # null until the Deck is read
    outline_source: str | None


class DocumentPatch(BaseModel):
    kind: Kind | None = None
    subject: str | None = Field(None, max_length=100)  # null files it back under "unassigned"
    title: str | None = Field(None, min_length=1, max_length=200)
    position: int | None = Field(None, ge=0)


class OutlineAiIn(BaseModel):
    provider: Provider = "anthropic"
    model: str | None = None

    @model_validator(mode="after")
    def _model(self):
        self.model = resolve_model(self.provider, self.model)
        return self


def _out(d: Document, subject: str | None) -> DocumentOut:
    return DocumentOut(
        id=d.id,
        title=d.title,
        kind=d.kind,
        subject=subject,
        position=d.position,
        page_count=d.page_count,
        outline=d.outline,
        outline_source=d.outline_source,
    )


def _by_sha(db: Session, user: User, sha: str) -> Document | None:
    return db.scalar(select(Document).where(Document.user_id == user.id, Document.sha256 == sha))


def _duplicate(db: Session, existing: Document, subject: str, response: Response) -> dict:
    """The answer for a PDF the user already has: the Deck itself in the same Subject, else a conflict naming where it lives (it is not moved)."""
    filed = db.scalar(select(Course.name).where(Course.id == existing.course_id))
    same = db.scalar(
        select(Course.id).where(Course.id == existing.course_id, func.lower(Course.name) == func.lower(subject))
    )  # as course_id compares
    if same is None:
        raise HTTPException(409, detail={"code": "already_uploaded", "document_id": str(existing.id), "subject": filed})
    response.status_code = 200
    return {"job_id": None, "document_id": existing.id}


def _next_position(db: Session, user: User, course: uuid.UUID | None) -> int:
    same_group = Document.course_id.is_(None) if course is None else Document.course_id == course
    return db.scalar(select(func.coalesce(func.max(Document.position) + 1, 0)).where(Document.user_id == user.id, same_group))


def _own(db: Session, user: User, document_id: uuid.UUID) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or doc.user_id != user.id:  # a foreign id looks like a missing one
        raise HTTPException(404)
    return doc


@router.post("/documents", status_code=202)
def upload_document(
    response: Response,
    file: UploadFile = File(...),
    kind: Kind = Form("slides"),
    subject: str | None = Form(None),
    title: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Queues the PDF for the worker. Follow GET /jobs/{job_id}/events; an already stored file answers with its document and no job."""
    if file.file.read(5) != b"%PDF-":
        raise HTTPException(400, detail={"code": "not_pdf"})
    file.file.seek(0)
    name = clean(subject)
    if not name:
        raise HTTPException(422, detail={"code": "subject_required"})
    filename = clean(file.filename, 255) or "upload.pdf"
    job = Job(id=uuid.uuid4(), kind="document", filename=filename, user_id=user.id)
    path = upload_path(job.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    sha = save_capped(file.file, path, MAX_BYTES)
    if existing := _by_sha(db, user, sha):
        path.unlink(missing_ok=True)
        return _duplicate(db, existing, name, response)
    course = course_id(db, user.id, name)
    doc = Document(
        user_id=user.id,
        course_id=course,
        kind=kind,
        title=clean(title, 200) or clean(re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE), 200) or "upload",
        position=_next_position(db, user, course),
        filename=filename,
        sha256=sha,
    )
    try:
        db.add(doc)
        db.flush()
        job.document_id = doc.id
        db.add(job)
        db.commit()
    except IntegrityError:  # a second identical upload won the UNIQUE(user_id, sha256) race
        db.rollback()
        path.unlink(missing_ok=True)
        if not (winner := _by_sha(db, user, sha)):
            raise
        return _duplicate(db, winner, name, response)
    response.headers["Location"] = f"/api/jobs/{job.id}"
    return {"job_id": job.id, "document_id": doc.id}


@router.get("/documents")
def list_documents(subject: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[DocumentOut]:
    """One subject's Decks in reading order, or (no subject) all of the user's Decks; subject null means unfiled."""
    q = select(Document, Course.name).outerjoin(Course, Document.course_id == Course.id).where(Document.user_id == user.id)
    if subject:
        q = q.where(func.lower(Course.name) == subject.strip().lower())
    return [_out(d, name) for d, name in db.execute(q.order_by(Document.position, Document.created_at))]


@router.get("/documents/{document_id}")
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> DocumentOut:
    doc = _own(db, user, document_id)
    return _out(doc, db.scalar(select(Course.name).where(Course.id == doc.course_id)))


@router.patch("/documents/{document_id}")
def patch_document(document_id: uuid.UUID, body: DocumentPatch, db: Session = Depends(get_db), user: User = Depends(current_user)) -> DocumentOut:
    doc = _own(db, user, document_id)
    if "subject" in body.model_fields_set:
        name = clean(body.subject)
        course = course_id(db, user.id, name) if name else None
        if course != doc.course_id:  # filed at the end of its new group; body.position may override
            doc.course_id, doc.position = course, _next_position(db, user, course)
    if body.kind is not None:
        doc.kind = body.kind
    if body.title is not None:
        doc.title = clean(body.title, 200) or doc.title
    if body.position is not None:
        doc.position = body.position
    db.commit()
    return _out(doc, db.scalar(select(Course.name).where(Course.id == doc.course_id)))


def _outline_pages(db: Session, user: User, document_id: uuid.UUID) -> list[tuple[int, str, str]]:
    doc = _own(db, user, document_id)
    rows = db.execute(select(DeckPage.page, DeckPage.title, DeckPage.body).where(DeckPage.document_id == doc.id).order_by(DeckPage.page)).all()
    if not rows:  # not read yet
        raise HTTPException(409, detail={"code": "not_read"})
    return [tuple(r) for r in rows]


def _save_outline(db: Session, user: User, document_id: uuid.UUID, outline: list[dict], source: str) -> DocumentOut:
    doc = _own(db, user, document_id)
    doc.outline, doc.outline_source = outline, source
    db.commit()
    return _out(doc, db.scalar(select(Course.name).where(Course.id == doc.course_id)))


@router.post("/documents/{document_id}/outline/ai")
async def outline_ai(
    document_id: uuid.UUID, body: OutlineAiIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> DocumentOut:
    """Replace the Outline with one the student's LLM makes from page titles and openings; the key comes in the header, never stored or logged."""
    key = request.headers.get("x-llm-key", "").strip()
    if not key:
        raise HTTPException(400, detail={"code": "no_key"})
    rows = await read_then_release(db, _outline_pages, user, document_id)  # the LLM call can take minutes
    if not ask_limiter.allow(str(user.id)):
        raise HTTPException(429, detail={"code": "rate_limited"})
    try:
        out = await complete(body.provider, body.model, key, rag_outline.SYSTEM, rag_outline.items(rows), rag_outline.AiOutline)
    except GradingError as e:
        raise HTTPException(
            429 if e.code == "rate_limited" else 400 if e.code in ("bad_key", "no_credits", "refused") else 502, detail={"code": e.code}
        ) from None
    outline = rag_outline.from_ai(out, len(rows))
    if not outline:
        raise HTTPException(502, detail={"code": "llm_failed"})
    return await run_in_threadpool(_save_outline, db, user, document_id, outline, "ai")


@router.post("/documents/{document_id}/outline/reset")
def outline_reset(document_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> DocumentOut:
    """Rebuild the automatic Outline from the stored PDF (bookmarks are not kept in the page rows)."""
    doc = _own(db, user, document_id)
    if not doc.page_count:  # the worker has not read it yet and will build the Outline itself
        raise HTTPException(409, detail={"code": "not_read"})
    try:
        pages = read_deck(doc_dir(doc.id) / "file.pdf")
    except Exception as e:
        log.warning("outline reset of %s failed: %s", doc.id, type(e).__name__)
        raise HTTPException(502, detail={"code": "unreadable"}) from None
    return _save_outline(db, user, document_id, rag_outline.build_outline(pages), "automatic")


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    doc = _own(db, user, document_id)
    db.delete(doc)  # chunks go with it (ON DELETE CASCADE)
    db.commit()
    shutil.rmtree(doc_dir(document_id), ignore_errors=True)


@router.get("/documents/{document_id}/file")
def document_file(document_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _own(db, user, document_id)
    path = doc_dir(document_id) / "file.pdf"
    if not path.is_file():  # still processing
        raise HTTPException(404)
    return FileResponse(path, media_type="application/pdf")  # no filename: shown inline, not downloaded
