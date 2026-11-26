"""Chats: a Subject's saved conversations. Every message is stored and runs the free Search; the result refs are stored as a search turn."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core import config
from ..db.exams import course_id
from ..db.models import Chat, Course, User
from ..db.session import get_db, read_then_release
from ..grading.grader import GradingError, complete
from ..grading.limits import ask_limiter
from ..grading.models import Provider, resolve_model
from ..rag import ask as rag_ask
from ..rag.find import run_search
from .auth import current_user

router = APIRouter()

TITLE_LEN = 60
NEW_TITLE = "New chat"


class ChatIn(BaseModel):
    subject: str = Field(min_length=1, max_length=100)


class RenameIn(BaseModel):
    title: str = Field(max_length=200)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class Pin(BaseModel):
    document_id: uuid.UUID
    page: int = Field(ge=1)


class PinsIn(BaseModel):
    pins: list[Pin] = Field(max_length=rag_ask.MAX_PINS)


class AskTurnIn(BaseModel):
    provider: Provider = "anthropic"
    model: str | None = None

    @model_validator(mode="after")
    def _model(self):
        self.model = resolve_model(self.provider, self.model)
        return self


def _out(c: Chat, *, full: bool = False) -> dict:
    out = {"id": str(c.id), "title": c.title, "updated_at": c.updated_at.isoformat()}
    return {**out, "messages": c.messages, "pinned": c.pinned} if full else out


def _own(db: Session, user: User, chat_id: uuid.UUID, *, lock: bool = False) -> tuple[Chat, Course]:
    q = select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id)
    chat = db.scalar(q.with_for_update().execution_options(populate_existing=True) if lock else q)  # populate_existing: the row, not a stale copy
    if chat is None:  # a foreign id looks like a missing one
        raise HTTPException(404)
    return chat, db.get(Course, chat.course_id)


@router.get("/chats")
def list_chats(subject: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[dict]:
    """The Subject's Chats, most recently used first."""
    q = (
        select(Chat)
        .join(Course, Chat.course_id == Course.id)
        .where(Chat.user_id == user.id, func.lower(Course.name) == subject.strip().lower())
        .order_by(Chat.updated_at.desc())
    )
    return [_out(c) for c in db.scalars(q)]


@router.post("/chats")
def create_chat(body: ChatIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    chat = Chat(user_id=user.id, course_id=course_id(db, user.id, body.subject.strip()), title=NEW_TITLE, messages=[], pinned=[])
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return _out(chat, full=True)


@router.get("/chats/{chat_id}")
def get_chat(chat_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return _out(_own(db, user, chat_id)[0], full=True)


@router.patch("/chats/{chat_id}")
def rename_chat(chat_id: uuid.UUID, body: RenameIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    chat, _ = _own(db, user, chat_id)
    title = body.title.replace("\x00", "").strip()
    if not title:
        raise HTTPException(422, detail={"code": "empty_title"})
    chat.title = title
    db.commit()
    return _out(chat)


@router.delete("/chats/{chat_id}", status_code=204)
def delete_chat(chat_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> None:
    db.delete(_own(db, user, chat_id)[0])
    db.commit()


@router.post("/chats/{chat_id}/messages")
def post_message(chat_id: uuid.UUID, body: MessageIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """Stores the message and a search turn with the results found for it; the first message also titles the Chat (no LLM)."""
    text = body.text.replace("\x00", "").strip()
    if not text:
        raise HTTPException(422, detail={"code": "empty_message"})
    _, course = _own(db, user, chat_id)
    found = jsonable_encoder(run_search(db, user.id, course.name, text))  # slow: before the row lock
    chat, _ = _own(db, user, chat_id, lock=True)  # two messages at once must both land
    if not chat.messages and chat.title == NEW_TITLE:  # a title the student chose before the first message stays
        chat.title = text if len(text) <= TITLE_LEN else text[: TITLE_LEN - 1].rstrip() + "…"
    # shortcut: the whole message list is rewritten per message, fine for conversations of a few hundred turns; split into rows if they grow
    chat.messages = [*chat.messages, {"role": "user", "text": text}, {"role": "search", **found}]
    db.commit()
    db.refresh(chat)
    return _out(chat, full=True)


@router.put("/chats/{chat_id}/pinned")
def set_pinned(chat_id: uuid.UUID, body: PinsIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """Replaces the pinned pages; pages that are not the user's, or not in this Subject, are dropped."""
    chat, course = _own(db, user, chat_id, lock=True)
    asked = [{"document_id": str(d), "page": n} for d, n in dict.fromkeys((p.document_id, p.page) for p in body.pins)]
    kept = {(p.document_id, p.page) for p in rag_ask.pages(db, user.id, course.id, asked)}
    chat.pinned = [p for p in asked if (uuid.UUID(p["document_id"]), p["page"]) in kept]
    db.commit()
    return _out(chat, full=True)


def _turn(db: Session, user: User, chat_id: uuid.UUID) -> tuple[list[dict], list[rag_ask.Page]]:
    chat, course = _own(db, user, chat_id)
    pinned = rag_ask.pages(db, user.id, course.id, chat.pinned)
    if not pinned:
        raise HTTPException(422, detail={"code": "no_pins"})
    if rag_ask.question(chat.messages) is None:
        raise HTTPException(422, detail={"code": "no_question"})
    return chat.messages, pinned


def _save_turn(db: Session, user: User, chat_id: uuid.UUID, turn: dict) -> dict:
    chat, _ = _own(db, user, chat_id, lock=True)  # a message sent meanwhile must not be lost
    chat.messages = [*chat.messages, turn]
    db.commit()
    db.refresh(chat)
    return _out(chat, full=True)


@router.post("/chats/{chat_id}/ask")
async def ask_turn(chat_id: uuid.UUID, body: AskTurnIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """The AI turn: answers from the pinned pages and the last messages with the caller's own LLM key (header only, never stored or logged)."""
    key = request.headers.get("x-llm-key", "").strip()
    if not key:
        raise HTTPException(400, detail={"code": "no_key"})
    messages, pinned = await read_then_release(db, _turn, user, chat_id)  # the LLM call can take minutes
    if not ask_limiter.allow(str(user.id)):
        raise HTTPException(429, detail={"code": "rate_limited"})
    try:
        out = await complete(body.provider, body.model, key, rag_ask.SYSTEM, rag_ask.items(messages, pinned), rag_ask.AskOut)
    except GradingError as e:
        raise HTTPException(
            429 if e.code == "rate_limited" else 400 if e.code in ("bad_key", "no_credits", "refused") else 502, detail={"code": e.code}
        ) from None
    turn = {"role": "ai", "text": out.answer, "cited": rag_ask.citations(out, pinned), "provider": body.provider, "model": body.model}
    return await run_in_threadpool(_save_turn, db, user, chat_id, turn)


@router.post("/chats/{chat_id}/ask/preview")
def ask_preview(chat_id: uuid.UUID, body: AskTurnIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """Dev only: the request the AI turn would send, without calling the LLM (and without a key)."""
    if not config.DEV:
        raise HTTPException(404)
    messages, pinned = _turn(db, user, chat_id)
    return {"provider": body.provider, "model": body.model, "system": rag_ask.SYSTEM, "prompt": rag_ask.items(messages, pinned)[0].text}
