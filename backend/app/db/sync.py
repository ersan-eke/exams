"""Wire format of device sync: camelCase JSON, times as epoch ms, maps keyed by subtask key ("A2b")."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator
from pydantic.alias_generators import to_camel

from ..grading.models import RubricLine
from ..pipeline.models import ExamStructure, McRule
from .models import Exam

Int32 = Annotated[int, Field(ge=0, le=2**31 - 1)]  # the Integer columns: more is a database error, not a 422
EpochMs = Annotated[int, Field(ge=0, le=253_402_300_799_000)]  # up to year 9999, what a datetime can hold


def ms(d: datetime) -> int:
    return round(d.timestamp() * 1000)


def dt(m: int) -> datetime:
    return datetime.fromtimestamp(m / 1000, UTC)


class ExamMeta(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: uuid.UUID
    title: str
    has_ink: bool = False
    hidden: bool = False
    subject: str | None = None
    point_overrides: dict[str, float] | None = None
    rubrics: dict[str, list[RubricLine]] | None = None
    solution_for: uuid.UUID | None = None
    fingerprint: str | None = None
    created_at: EpochMs = 0
    edited_at: EpochMs = 0  # old clients omit it: epoch, so any stored edit wins


class ExamPut(ExamMeta):
    structure: ExamStructure | None = None
    images: dict[str, str] | None = None  # crop name -> base64 PNG
    solution_images: dict[str, str] | None = None

    @model_validator(mode="after")
    def _unique_ids(self):
        tasks = self.structure.tasks if self.structure else []
        ids = [t.id for t in tasks] + [f"{t.id}/{s.id}" for t in tasks for s in t.subtasks]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate task or subtask ids")
        return self


def exam_meta(e: Exam, subject: str | None) -> ExamMeta:
    return ExamMeta(
        id=e.id, title=e.title, has_ink=e.has_ink, hidden=e.hidden, subject=subject,
        point_overrides=e.point_overrides, rubrics=e.rubrics, solution_for=e.solution_for,
        fingerprint=e.fingerprint, created_at=ms(e.created_at), edited_at=ms(e.edited_at),
    )  # fmt: skip


class _Wire(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AnswerWire(_Wire):
    mode: Literal["type", "draw"]
    parts: list[dict[str, Any]]  # text + strokes per answer box, stored whole
    done: bool = False
    ticks: list[Int32] = []


class TimeWire(_Wire):
    main: Int32
    over: Int32


class GradeWire(_Wire):
    main: float | None = None
    over: float | None = None
    comment: str | None = None
    marks: dict[str, Any] | None = None
    llm: dict[str, Any] | None = None

    @model_serializer(mode="wrap")
    def _omit_unset(self, handler):  # the client's Grade fields are optional: absent, never null
        return {k: v for k, v in handler(self).items() if v is not None}


class AttemptWire(_Wire):
    """The client's Attempt without `view`. Only handed-in attempts sync."""

    id: uuid.UUID
    exam_id: uuid.UUID
    solution_exam_id: uuid.UUID | None = None  # old clients omit it
    status: Literal["handed_in"]
    fresh: bool
    started_at: EpochMs
    time_limit_ms: Int32
    included_task_ids: list[str]
    attendance_at: Int32 | None
    attendance_done: bool
    mc_rule: McRule
    extended: bool
    answers: dict[str, AnswerWire]
    snapshot: dict[str, AnswerWire] | None
    handed_in_at: EpochMs | None
    time: dict[str, TimeWire]
    grades: dict[str, GradeWire]
    graded_at: EpochMs | None = None
    edited_at: EpochMs = 0


class SyncOut(_Wire):
    cursor: str
    more: bool = False  # the page was full: ask again with since=page_since and after=after
    after: uuid.UUID | None = None
    page_since: str | None = None
    exams: list[ExamMeta]
    attempts: list[AttemptWire]
