"""The few course excerpts that go into a grading request when there is no solution sheet."""

import logging
import uuid
from collections.abc import Sequence

from ..db.session import SessionLocal
from .search import MIN_SIM, find_course, search

log = logging.getLogger(__name__)

MAX_CHARS = 1500  # the whole block, so the request stays small
HITS = 3


def material_for(session_cookie: str | None, subject: str, text: str, exclude_exams: Sequence[uuid.UUID] = ()) -> str:
    """Text excerpts of the signed-in caller's material that match `text`, or "" (signed out, no material, or any failure:
    grading must never fail because of the extras)."""
    from ..api.auth import session_user

    try:
        with SessionLocal() as db:
            user = session_user(db, session_cookie)
            course = user and find_course(db, user.id, subject)
            if not course:
                return ""
            hits = [h for h in search(db, user.id, course, [text], exclude_exams=exclude_exams, k=HITS) if h.sim >= MIN_SIM]
        block, budget = [], MAX_CHARS
        for h in hits:
            label = f"{h.title}, p. {h.page}" if h.page else f"{h.title}, task {h.subtask_key}"
            piece = f"[{label}]\n{h.text}"[:budget]
            block.append(piece)
            budget -= len(piece)
            if budget <= 0:
                break
        return "\n\n".join(block)
    except Exception as e:  # only the type: messages can carry user text
        log.warning("material lookup failed: %s", type(e).__name__)
        return ""
