"""The AI turn of a Chat: an answer from the pinned pages only, plus the last few messages. Only cited ids that were pinned survive."""

import uuid
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from ..db.models import DeckPage, Document
from ..grading.prompt import Text

HISTORY = 6  # messages (the student's and the AI's) that go along
MAX_PINS = 20

SYSTEM = """You answer a student's question about their course using only the numbered pages (lecture slides, scripts, exercises) they \
pinned. Cite the numbers of the pages you used in `cited`. If the pages do not answer the question, say so briefly and cite nothing. \
Be concise, plain text, no Markdown, in the language of the question. Reply with the JSON object only."""


class AskOut(BaseModel):
    answer: str
    cited: list[int]


@dataclass
class Page:
    document_id: uuid.UUID
    page: int
    label: str  # "Deck · 3-21" or "Deck · p. 21"
    text: str


def pages(db: Session, user_id: uuid.UUID, course: uuid.UUID, pins: list[dict]) -> list[Page]:
    """The pinned pages that are still the user's and in this Subject, in pin order (unknown pins are dropped)."""
    keys = [(uuid.UUID(p["document_id"]), p["page"]) for p in pins]
    if not keys:
        return []
    rows = db.execute(
        select(DeckPage, Document.title)
        .join(Document, DeckPage.document_id == Document.id)
        .where(Document.user_id == user_id, Document.course_id == course, tuple_(DeckPage.document_id, DeckPage.page).in_(keys))
    ).all()
    by_key = {(p.document_id, p.page): (p, deck) for p, deck in rows}
    return [
        Page(k[0], k[1], f"{by_key[k][1]} · {by_key[k][0].label or f'p. {k[1]}'}", f"{by_key[k][0].title}\n{by_key[k][0].body}".strip())
        for k in keys
        if k in by_key
    ]


def question(messages: list[dict]) -> str | None:
    """The newest message of the student, which the turn answers."""
    return next((m["text"] for m in reversed(messages) if m["role"] == "user"), None)


def items(messages: list[dict], pinned: list[Page]) -> list[Text]:
    talk = [m for m in messages if m["role"] in ("user", "ai")][-HISTORY:]
    pages_text = "\n\n".join(f"[{i}] {p.label}\n{p.text}" for i, p in enumerate(pinned, 1))
    history = "\n".join(f"{'Student' if m['role'] == 'user' else 'You'}: {m['text']}" for m in talk)
    return [Text(f"Pinned pages:\n\n{pages_text}\n\nConversation:\n{history}")]


def citations(out: AskOut, pinned: list[Page]) -> list[dict]:
    cited = dict.fromkeys(i for i in out.cited if 1 <= i <= len(pinned))  # numbers the model made up are dropped
    return [{"document_id": str(pinned[i - 1].document_id), "page": pinned[i - 1].page, "label": pinned[i - 1].label} for i in cited]
