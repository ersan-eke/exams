"""Everything searchable gets indexed here, never in a web request (they must not load the embedding model).
Exam subtasks become chunks: the worker calls `index_pending` while idle, so uploads, syncs, edits (which replace the subtask rows)
and the first run on an existing database are all covered by one mechanism. A Deck's pages are stored by `store_deck`
(the upload) and `backfill_decks` (Decks that predate page structure or Outlines)."""

import logging
import uuid

from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session

from ..core.storage import doc_dir
from ..db.models import Chunk, DeckPage, Document, Exam, Subtask, Task
from . import embed
from .chunk import MAX_CHARS, split
from .deck import PageRead, read_deck
from .outline import build_outline

log = logging.getLogger(__name__)
_unreadable: set[uuid.UUID] = set()  # shortcut: forgotten on restart, so a Deck that cannot be read is retried then; store a flag if that gets noisy


def index_pending(db: Session, limit: int = 100) -> int:
    """Embed up to `limit` account-owned subtasks that have no chunk yet; returns how many were indexed."""
    rows = db.execute(
        select(Subtask.id, Task.title, Subtask.text, Subtask.solution_text)
        .join(Task, Subtask.task_id == Task.id)
        .join(Exam, Task.exam_id == Exam.id)
        .where(
            Exam.user_id.is_not(None),
            ~exists().where(Chunk.subtask_id == Subtask.id),
            func.length(func.btrim(Subtask.text + Subtask.solution_text)) > 0,  # nothing to search for otherwise, and it would stay pending forever
        )
        .limit(limit)
    ).all()
    if not rows:
        return 0
    texts = ["\n".join(p for p in (title, text, solution) if p.strip())[:MAX_CHARS] for _, title, text, solution in rows]
    db.add_all(Chunk(subtask_id=sid, text=t, embedding=v) for (sid, *_), t, v in zip(rows, texts, embed.embed(texts), strict=True))
    db.commit()
    return len(rows)


def store_deck(db: Session, doc: Document, pages: list[PageRead]) -> None:
    """Replace the Deck's page rows and chunks with these pages (embedding them), record the page count and build the automatic Outline."""
    pieces = [(p.page, t) for p in pages for t in split(p.body)]
    vectors = embed.embed([t for _, t in pieces])
    db.execute(delete(DeckPage).where(DeckPage.document_id == doc.id))
    db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    db.add_all(
        DeckPage(document_id=doc.id, page=p.page, label=p.label, title=p.title, section=p.section, headings=p.headings, body=p.body) for p in pages
    )
    db.add_all(Chunk(document_id=doc.id, page=page, text=t, embedding=v) for (page, t), v in zip(pieces, vectors, strict=True))
    doc.page_count = len(pages)
    doc.outline, doc.outline_source = build_outline(pages), "automatic"


def backfill_decks(db: Session) -> int:
    """Read one finished Deck that has no Outline yet from its stored PDF; returns how many were handled (also when it was unreadable)."""
    doc = db.scalar(select(Document).where(Document.outline_source.is_(None), Document.id.not_in(_unreadable)).limit(1))
    if doc is None:
        return 0
    try:
        pages = read_deck(doc_dir(doc.id) / "file.pdf")
        if not any(p.body for p in pages):
            raise ValueError("no text")
        store_deck(db, doc, pages)
        db.commit()
    except Exception as e:  # only the type: messages can carry document text
        db.rollback()
        _unreadable.add(doc.id)
        log.warning("deck %s not backfilled: %s", doc.id, type(e).__name__)
    return 1
