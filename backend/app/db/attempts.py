"""AttemptWire (client shape) <-> attempts/answers/subtask_times/grades rows.

Overtime: with extra time the client keeps `snapshot` (answers when time ran out) and `answers` (after it);
rows call them `main` and `over`. Without it only `main` exists and holds `answers`."""

import uuid
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import Answer, Attempt, Grade, Subtask, SubtaskTime, Task
from .sync import AnswerWire, AttemptWire, GradeWire, TimeWire, dt, ms


def subtask_keys(db: Session, exam_id: uuid.UUID) -> dict[str, int]:
    rows = db.execute(select(Subtask.key, Subtask.id).join(Task).where(Task.exam_id == exam_id))
    return {k: i for k, i in rows}


def _ids(keys: dict[str, int], used) -> None:
    unknown = set(used) - keys.keys()
    if unknown:
        raise ValueError(f"unknown subtasks {sorted(unknown)}")


def write_attempt(db: Session, user_id: uuid.UUID, a: AttemptWire, keys: dict[str, int]) -> None:
    """Upsert the attempt and replace its children. Raises ValueError on unknown subtask keys; does not commit."""
    for m in (a.answers, a.snapshot or {}, a.time, a.grades):
        _ids(keys, m)
    overtime = a.snapshot is not None
    cols = dict(
        user_id=user_id, exam_id=a.exam_id, solution_exam_id=a.solution_exam_id, status=a.status, fresh=a.fresh,
        started_at=dt(a.started_at), time_limit_ms=a.time_limit_ms, included_task_ids=a.included_task_ids,
        attendance_at_ms=a.attendance_at, attendance_done=a.attendance_done,
        mc_rule=a.mc_rule.model_dump(exclude_unset=True), extended=a.extended, overtime=overtime,
        edited_at=dt(a.edited_at), handed_in_at=dt(a.handed_in_at) if a.handed_in_at is not None else None,
        graded_at=dt(a.graded_at) if a.graded_at is not None else None,
    )  # fmt: skip
    row = db.get(Attempt, a.id)
    if row is None:
        db.add(Attempt(id=a.id, **cols))
        db.flush()
    else:
        for k, v in cols.items():
            setattr(row, k, v)
        for t in (Answer, SubtaskTime, Grade):
            db.execute(delete(t).where(t.attempt_id == a.id))
    versions = [("main", a.snapshot), ("over", a.answers)] if overtime else [("main", a.answers)]
    for version, m in versions:
        for k, v in m.items():
            db.add(Answer(attempt_id=a.id, subtask_id=keys[k], version=version, **v.model_dump(by_alias=False)))
    for k, t in a.time.items():
        db.add(SubtaskTime(attempt_id=a.id, subtask_id=keys[k], main_ms=t.main, over_ms=t.over))
    for k, g in a.grades.items():
        db.add(Grade(attempt_id=a.id, subtask_id=keys[k], **g.model_dump(exclude_none=True)))


def read_attempt(row: Attempt, keys_by_id: dict[int, str]) -> AttemptWire:
    answers = {v: {} for v in ("main", "over")}
    for x in row.answers:
        answers[x.version][keys_by_id[x.subtask_id]] = AnswerWire(mode=x.mode, parts=x.parts, done=x.done, ticks=x.ticks)
    grade = lambda g: GradeWire(main=_f(g.main), over=_f(g.over), comment=g.comment, marks=g.marks, llm=g.llm)
    return AttemptWire(
        id=row.id, exam_id=row.exam_id, solution_exam_id=row.solution_exam_id, status=row.status, fresh=row.fresh,
        started_at=ms(row.started_at), time_limit_ms=row.time_limit_ms, included_task_ids=row.included_task_ids,
        attendance_at=row.attendance_at_ms, attendance_done=row.attendance_done, mc_rule=row.mc_rule,
        extended=row.extended,
        answers=answers["over"] if row.overtime else answers["main"],
        snapshot=answers["main"] if row.overtime else None,
        handed_in_at=ms(row.handed_in_at) if row.handed_in_at else None,
        time={keys_by_id[t.subtask_id]: TimeWire(main=t.main_ms, over=t.over_ms) for t in row.times},
        grades={keys_by_id[g.subtask_id]: grade(g) for g in row.grades},
        graded_at=ms(row.graded_at) if row.graded_at else None,
        edited_at=ms(row.edited_at),
    )  # fmt: skip


def _f(d: Decimal | None) -> float | None:
    return None if d is None else float(d)
