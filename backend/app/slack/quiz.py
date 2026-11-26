import random
import uuid
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Integration
from ..mcp import tools
from . import blocks, crops

WEAKEST = 10


def linked_user(db: Session, team_id: str, slack_user_id: str) -> uuid.UUID | None:
    return db.scalar(
        select(Integration.user_id).where(
            Integration.provider == "slack", Integration.workspace_id == team_id, Integration.external_user_id == slack_user_id
        )
    )


def _exam_url(base: str, ref: str) -> str:
    exam, _, key = ref.partition("/")
    return f"{base}/exams/{exam}/view?subtask={quote(key)}"


def _subjects(db: Session, user_id: uuid.UUID, lead: str) -> dict:
    names = [s["subject"] for s in tools.list_subjects(db, user_id)]
    return blocks.message(f"{lead} Your subjects: {', '.join(blocks.esc(n) for n in names)}" if names else "You have no exams yet.")


def question(db: Session, user_id: uuid.UUID, subject: str, base: str = "") -> dict:
    subject = subject.strip()
    if not subject:
        return _subjects(db, user_id, "Usage: /quiz <subject>.")
    try:
        rows = [r for r in tools.find_tasks(db, user_id, subject, None, None, limit=None) if r["preview"].strip()]
    except (tools.NotFound, tools.BadInput):
        return _subjects(db, user_id, "Unknown subject.")
    if not rows:
        return blocks.message(f"No questions with text in {blocks.esc(subject)}.")
    # the weakest by the latest score come first, never-attempted ones count as middling; a random pick among the WEAKEST keeps it varied
    rows.sort(key=lambda r: (0.5 if r["last_score_share"] is None else r["last_score_share"], random.random()))  # random tiebreak
    ref = random.choice(rows[:WEAKEST])["id"]
    task, paths = tools.get_task(db, user_id, ref, False)
    urls = [crops.crop_url(base, p) for p in [*tools.context_crops(db, user_id, ref), *paths]]
    out = blocks.question_blocks(task, urls, _exam_url(base, ref))
    return blocks.message(f"{blocks.esc(task['exam'])}: {blocks.esc(task['text'][:200])}", out)


def answer(db: Session, user_id: uuid.UUID, ref: str, choice: int | None, base: str = "") -> dict:
    try:
        task, paths = tools.get_task(db, user_id, ref, True)
        _, question_paths = tools.get_task(db, user_id, ref, False)
        context = tools.context_crops(db, user_id, ref)
    except (tools.NotFound, tools.BadInput):
        return blocks.message("Question not found.")
    urls = [crops.crop_url(base, p) for p in [*context, *paths]]
    n = len(context) + len(question_paths)  # the solution call returns the question crops first
    out = blocks.answer_blocks(task, ref, choice, urls[:n], urls[n:], _exam_url(base, ref))
    return blocks.message(blocks.verdict(task, choice) or "Solution", out)
