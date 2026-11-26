"""ExamStructure (the API/pipeline contract) <-> exams/tasks/subtasks rows. Column names mirror the
Pydantic field names, except the Pydantic `id` ("A2b") which is the row's `key`."""

import uuid

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..pipeline import models as p
from .models import Course, Exam, Subtask, Task


def course_id(db: Session, user_id: uuid.UUID, name: str) -> uuid.UUID:
    """Find or create the user's course; the conflict clause keeps two workers from making it twice."""
    db.execute(insert(Course).values(user_id=user_id, name=name).on_conflict_do_nothing(index_elements=[Course.user_id, func.lower(Course.name)]))
    return db.scalars(select(Course.id).where(Course.user_id == user_id, func.lower(Course.name) == func.lower(name))).one()


def to_rows(exam_id: uuid.UUID, s: p.ExamStructure, **exam_cols) -> Exam:
    """exam_cols: the columns the pipeline doesn't know (title, user_id, has_ink, ...)."""
    return Exam(
        id=exam_id,
        **exam_cols,
        **s.model_dump(mode="json", exclude={"tasks"}),
        tasks=[
            Task(
                position=i,
                key=t.id,
                **t.model_dump(mode="json", exclude={"id", "subtasks"}),
                subtasks=[Subtask(position=j, key=st.id, **st.model_dump(mode="json", exclude={"id"})) for j, st in enumerate(t.subtasks)],
            )
            for i, t in enumerate(s.tasks)
        ],
    )


def _pick(row, model: type[BaseModel], **override) -> dict:
    return {f: getattr(row, f) for f in model.model_fields.keys() - override.keys()} | override


def from_rows(e: Exam) -> p.ExamStructure:
    return p.ExamStructure.model_validate(
        _pick(
            e,
            p.ExamStructure,
            tasks=[_pick(t, p.Task, id=t.key, subtasks=[_pick(st, p.Subtask, id=st.key) for st in t.subtasks]) for t in e.tasks],
        )
    )
