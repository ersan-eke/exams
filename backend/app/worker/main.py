"""Upload worker, run as: python -m app.worker.main

The jobs table is the queue. A job is claimed with SELECT ... FOR UPDATE SKIP LOCKED, so any number
of workers can run side by side without two of them taking the same job.
"""

import logging
import shutil
import time
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from ..core.storage import doc_dir, exam_dir, upload_path
from ..core.text import clean
from ..db.exams import course_id, to_rows
from ..db.models import Document, Exam, Job, LoginSession, WebhookEvent
from ..db.session import SessionLocal
from ..notion.export import ExportFailed, export_subject
from ..pipeline import extract, group, render_variants
from ..pipeline.enrich import enrich
from ..rag.deck import read_deck
from ..rag.index import backfill_decks, index_pending, store_deck

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
# shortcut: no heartbeat while a PDF stage runs (a Notion export beats per card), so a stage longer than this
# gets picked up by a second worker; add a heartbeat once a stage (e.g. OCR) can take that long
STALE = timedelta(minutes=15)
KEEP_ANONYMOUS = timedelta(hours=24)


class JobFailed(Exception):
    """A result about the PDF itself; running it again would fail the same way."""

    def __init__(self, code: str):
        self.code = code


def claim(db: Session) -> Job | None:
    job = db.scalars(
        select(Job)
        .where(or_(Job.status == "queued", (Job.status == "running") & (Job.locked_at < func.now() - STALE)))
        .order_by(Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if job:
        job.status, job.locked_at, job.attempts = "running", func.now(), job.attempts + 1
        db.commit()
    return job


def _stage(db: Session, job: Job, stage: str) -> None:
    job.stage, job.locked_at = stage, func.now()
    db.commit()


def process(db: Session, job: Job) -> uuid.UUID:
    pdf = upload_path(job.id)
    _stage(db, job, "extract")
    try:
        pages = extract(pdf)
    except Exception:
        raise JobFailed("unreadable")
    _stage(db, job, "enrich")
    # shortcut: no timeout around a docling hang; add one if the worker ever stalls here
    if job.attempts == 1:  # a crash-retry skips it: the crash may have been the enrichment
        enrich(pdf, pages)  # never raises; a no-op without mlx_vlm
    try:
        exam = group(pages, job.filename, pdf_path=pdf)
    except Exception:
        raise JobFailed("unreadable")
    if exam.kind == "scanned" or (not exam.tasks and any("scanned" in i.message.lower() for i in exam.issues)):
        raise JobFailed("scanned")
    if not exam.tasks:
        raise JobFailed("no_tasks")

    _stage(db, job, "render")
    exam_id = uuid.uuid4()
    try:
        dirs = render_variants(pdf, exam, pages, exam_dir(exam_id), ink=exam.is_solution or job.role == "solution")
    except Exception:
        shutil.rmtree(exam_dir(exam_id), ignore_errors=True)
        raise JobFailed("unreadable")
    # after rendering: the renderer fills in each region's crop file name
    course = course_id(db, job.user_id, job.subject) if job.user_id and job.subject else None
    db.add(
        to_rows(
            exam_id,
            exam,
            title=clean(Path(job.filename).stem, 200) or "upload",
            user_id=job.user_id,
            course_id=course,
            has_ink=dirs["ink"] is not None,
        )
    )
    return exam_id


def process_document(db: Session, job: Job) -> None:
    """Study PDF: page structure and text -> chunks -> embeddings. The PDF is kept for the viewer instead of deleted."""
    doc = job.document_id and db.get(Document, job.document_id)
    if doc is None:  # deleted while queued (the job's link is then NULL)
        return
    pdf = upload_path(job.id)
    _stage(db, job, "extract")
    try:
        pages = read_deck(pdf)
    except Exception:
        raise JobFailed("unreadable")
    if not any(p.body for p in pages):
        raise JobFailed("scanned")
    _stage(db, job, "embed")
    store_deck(db, doc, pages)
    dest = doc_dir(doc.id)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf, dest / "file.pdf")  # copy: the unlink in run_once then covers every outcome the same way


def run_once(db: Session) -> bool:
    """Process one job; False when the queue is empty."""
    job = claim(db)
    if job is None:
        return False
    try:
        if job.attempts > MAX_ATTEMPTS:  # crashed workers kept leaving it behind
            raise JobFailed("server")
        if job.kind == "document":
            process_document(db, job)
            db.flush()  # a Deck deleted meanwhile fails here, inside the try, and the retry finds no Deck
        elif job.kind == "notion":
            export_subject(db, job.user_id, job.course_id, on_card=lambda: _stage(db, job, "export"))
        else:
            job.exam_id = process(db, job)
        job.status = "done"
    except (JobFailed, ExportFailed) as e:
        job.status, job.error_code = "failed", e.code
    except Exception:
        db.rollback()  # first: after a failed flush the session cannot even read job.id
        log.exception("job %s crashed", job.id)
        job.status = "queued" if job.attempts < MAX_ATTEMPTS else "failed"
        job.error_code = None if job.status == "queued" else "server"
    if job.status != "queued":
        job.finished_at = func.now()
        if (
            job.error_code in ("unreadable", "scanned") and job.document_id
        ):  # a chapter without text is not worth a row; a server error is not the user's file's fault
            db.execute(delete(Document).where(Document.id == job.document_id))
            shutil.rmtree(doc_dir(job.document_id), ignore_errors=True)
    db.commit()
    if job.status != "queued":
        kept = doc_dir(job.document_id) / "file.pdf" if job.document_id else None
        if job.error_code == "server" and kept and not kept.exists():  # the Deck stays, so its PDF does too: backfill_decks reads it when idle
            kept.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(upload_path(job.id), kept)
        upload_path(job.id).unlink(missing_ok=True)  # exam PDFs are never kept (only crops and structure); a Deck's PDF was copied for the viewer
    return True


def cleanup(db: Session) -> None:
    """Without an account the server is a processing pipe, not storage: anonymous uploads go after a day.
    Expired login sessions go too."""
    cutoff = func.now() - KEEP_ANONYMOUS
    exam_ids = db.scalars(delete(Exam).where(Exam.user_id.is_(None), Exam.created_at < cutoff).returning(Exam.id)).all()
    db.execute(delete(Job).where(Job.user_id.is_(None), Job.created_at < cutoff, Job.status.in_(("done", "failed"))))
    db.execute(delete(LoginSession).where(LoginSession.expires_at < func.now()))
    db.execute(delete(WebhookEvent).where(WebhookEvent.received_at < func.now() - timedelta(days=7)))
    db.commit()
    for exam_id in exam_ids:
        shutil.rmtree(exam_dir(exam_id), ignore_errors=True)


_last_cleanup = 0.0


def step(db: Session) -> bool:
    """One pass of the loop; True when there may be more to do right away."""
    global _last_cleanup
    if run_once(db) or index_pending(db) or backfill_decks(db):
        return True
    if time.monotonic() - _last_cleanup > 3600:
        cleanup(db)
        _last_cleanup = time.monotonic()
    return False


def guarded_step() -> bool:
    """`step` in its own session; an error (a Deck deleted mid-job, Postgres restarting) is logged and the loop goes on."""
    try:
        with SessionLocal() as db:
            try:
                return step(db)
            except Exception:
                db.rollback()
                raise
    except Exception:
        log.exception("worker step failed")
        return False


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        if not guarded_step():
            time.sleep(1)  # shortcut: polls the queue; use LISTEN/NOTIFY if the 1s pickup delay starts to matter


if __name__ == "__main__":
    main()
