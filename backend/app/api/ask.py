"""Search over a subject's material, and the "where to read this" links under a subtask."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db.models import User
from ..db.session import get_db
from ..rag.find import run_search
from ..rag.hints import hints, vocabulary
from ..rag.search import MIN_SIM, find_course
from ..rag.slides import search_slides
from .auth import current_user

router = APIRouter()


class LookupIn(BaseModel):
    subject: str = Field(min_length=1, max_length=100)
    text: str = Field(max_length=2000)
    solution_text: str = Field("", max_length=2000)


class SearchIn(BaseModel):
    subject: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=1000)


@router.post("/materials/lookup")
def lookup(body: LookupIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[dict]:
    """The pages of this subject's material that best match a subtask (and its solution): at most two, one per page."""
    course = find_course(db, user.id, body.subject)
    hits = search_slides(db, user.id, course, [body.text, body.solution_text]) if course else []
    return [{"document_id": h.document_id, "title": h.deck, "page": h.page} for h in hits if h.sim >= MIN_SIM][:2]


@router.post("/search")
def search_subject(body: SearchIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return run_search(db, user.id, body.subject, body.query)


@router.get("/search/hints")
def search_hints(subject: str, text: str = Query("", max_length=1000), db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """Typing help for the Chat input: completions for the last word and a "Did you mean" for a misspelled one, from this Subject's titles only."""
    course = find_course(db, user.id, subject)
    return hints(vocabulary(db, user.id, course), text) if course else {"completions": [], "suggestion": None}
