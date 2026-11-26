"""The free Search every Chat message runs: slides of the Subject and the past exam tasks that fit."""

import uuid

from sqlalchemy.orm import Session

from .search import MIN_SIM, find_course, search
from .slides import search_slides


def run_search(db: Session, user_id: uuid.UUID, subject: str, query: str) -> dict:
    """Free, local search (no key, no LLM): the best five slides of the Subject, one per printed label, and the past exam tasks that fit."""
    course = find_course(db, user_id, subject)
    if not course:
        return {"slides": [], "exams": []}
    slides = [
        {"document_id": str(h.document_id), "deck": h.deck, "label": h.label, "page": h.page, "title": h.title, "weak": h.weak, "terms": h.terms}
        for h in search_slides(db, user_id, course, [query])
    ]
    exams = [
        {"exam_id": h.exam_id, "title": h.title, "subtask_key": h.subtask_key, "text": h.text[:200]}
        for h in search(db, user_id, course, [query], exams_only=True)
        if h.sim >= MIN_SIM
    ]
    return {"slides": slides, "exams": exams}
