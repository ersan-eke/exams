"""MCP tool logic as plain functions of (db, user_id, ...), so it is testable without the protocol."""

import math
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NotRequired, TypedDict

from sqlalchemy import Numeric, any_, case, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..core.storage import CROP_NAME, exam_dir
from ..db.attempts import read_attempt, subtask_keys, write_attempt
from ..db.exams import from_rows
from ..db.models import Answer, Attempt, Course, Exam, Grade, Subtask, Task
from ..db.scoring import match_solution, mc_keys, subtask_scores, with_overrides
from ..db.sync import AnswerWire, AttemptWire, GradeWire, TimeWire
from ..rag.search import similar_subtasks

# record_practice writes time_limit_ms=0, which the app never does (its timer would end at once): marks practice attempts
PRACTICE = Attempt.time_limit_ms == 0
# practice saved within this long of the last save joins the same attempt, so one session is one attempt in the app
PRACTICE_SESSION = timedelta(hours=3)


class BadInput(ValueError):
    """A tool argument the model got wrong; its message is meant for the model."""


class NotFound(ValueError):
    def __init__(self):
        super().__init__("not found")  # same text for unknown and foreign ids


def _practice_exams(user_id: uuid.UUID, course_id: uuid.UUID | None = None):
    """The user's visible exams that can be practiced (not solutions), optionally of one course."""
    q = select(Exam.id, Exam.course_id).where(Exam.user_id == user_id, ~Exam.hidden, ~Exam.is_solution, Exam.solution_for.is_(None))
    return q if course_id is None else q.where(Exam.course_id == course_id)


def max_points():
    """exam.point_overrides[key] else subtask.points; needs Exam and Subtask in the query. Scores use db.scoring instead."""
    return func.coalesce(Exam.point_overrides.op("->>")(Subtask.key).cast(Numeric), Subtask.points)


def subtask_max(exam: Exam, sub: Subtask) -> float | None:
    """max_points() for loaded rows."""
    m = (exam.point_overrides or {}).get(sub.key)
    m = sub.points if m is None else m
    return None if m is None else float(m)


def _share(got, mx) -> float | None:
    return round(float(got) / float(mx), 3) if mx else None


def _task_name(t: Task) -> str:
    return t.title or t.key


def _course(db: Session, user_id: uuid.UUID, name: str) -> Course:
    c = db.scalar(select(Course).where(Course.user_id == user_id, func.lower(Course.name) == func.lower(name)))
    if c is None:
        raise NotFound()
    return c


def resolve(db: Session, user_id: uuid.UUID, ref: str) -> tuple[Exam, Task, Subtask]:
    """A wire subtask id "<exam uuid>/<subtask key>" to its rows, if the exam is the user's."""
    exam_id, _, key = ref.partition("/")
    try:
        exam_id = uuid.UUID(exam_id)
    except ValueError:
        raise NotFound() from None
    row = db.execute(
        select(Exam, Task, Subtask)
        .join(Task, Task.exam_id == Exam.id)
        .join(Subtask, Subtask.task_id == Task.id)
        .where(Exam.id == exam_id, Exam.user_id == user_id, Subtask.key == key)
    ).first()
    if row is None:
        raise NotFound()
    return tuple(row)


def _solution_exam(db: Session, user_id: uuid.UUID, exam_id: uuid.UUID) -> Exam | None:
    """The exam's uploaded solution: the newest one linked to any of the user's attempts at it (it applies to the whole exam)."""
    sol = db.scalar(
        select(Attempt.solution_exam_id)
        .where(Attempt.user_id == user_id, Attempt.exam_id == exam_id, Attempt.solution_exam_id.is_not(None))
        .order_by(Attempt.started_at.desc())
        .limit(1)
    )
    e = db.get(Exam, sol) if sol else None
    return e if e is not None and e.user_id == user_id else None


class Scored(TypedDict):
    exam: Exam
    attempt: Attempt
    subtasks: dict[str, tuple[float, float | None]]  # key -> (points, max or None), as the app scores them


def _scored(db: Session, user_id: uuid.UUID, course_id: uuid.UUID | None = None) -> list[Scored]:
    """The user's graded, handed-in attempts at practice exams, scored like the app (MC auto points, MC point split)."""
    exams = _practice_exams(user_id, course_id).subquery()
    attempts = db.scalars(
        select(Attempt)
        .join(exams, exams.c.id == Attempt.exam_id)
        .where(Attempt.user_id == user_id, Attempt.status == "handed_in", Attempt.graded_at.is_not(None))
        .options(selectinload(Attempt.answers), selectinload(Attempt.times), selectinload(Attempt.grades))
    ).all()
    with_tasks = [selectinload(Exam.tasks).selectinload(Task.subtasks)]
    loaded, solutions, out = {}, {}, []
    for a in attempts:
        if a.exam_id not in loaded:
            exam = db.get(Exam, a.exam_id, options=with_tasks)
            fallback = None if exam.has_ink else _solution_exam(db, user_id, exam.id)
            keys_by_id = {s.id: s.key for t in exam.tasks for s in t.subtasks}
            loaded[a.exam_id] = (exam, with_overrides(from_rows(exam), exam.point_overrides), keys_by_id, fallback)
        exam, structure, keys_by_id, fallback = loaded[a.exam_id]
        sol = db.get(Exam, a.solution_exam_id, options=with_tasks) if a.solution_exam_id else fallback
        sol = sol if sol is not None and sol.user_id == user_id else fallback
        if sol is not None and sol.id not in solutions:
            solutions[sol.id] = from_rows(sol)
        keys = mc_keys(structure, solutions[sol.id] if sol else None)
        out.append(Scored(exam=exam, attempt=a, subtasks=subtask_scores(read_attempt(a, keys_by_id), structure, keys)))
    return out


def _sum(scores) -> list[float]:
    """[points, known max] over (points, max) pairs, as the app totals an attempt."""
    acc = [0.0, 0.0]
    for got, mx in scores:
        acc[0] += got
        acc[1] += mx or 0
    return acc


def _scores(scored: list[Scored]) -> dict:
    """Score share per course, the one both list_subjects and progress report."""
    per = defaultdict(list)
    for x in scored:
        per[x["exam"].course_id] += x["subtasks"].values()
    return {c: _share(*_sum(v)) for c, v in per.items()}


def list_subjects(db: Session, user_id: uuid.UUID) -> list[dict]:
    exams = _practice_exams(user_id).subquery()
    handed_in = (
        select(Attempt.id, exams.c.course_id)
        .join(exams, exams.c.id == Attempt.exam_id)
        .where(Attempt.user_id == user_id, Attempt.status == "handed_in")
        .subquery()
    )
    scores = _scores(_scored(db, user_id))
    exam_counts = dict(db.execute(select(exams.c.course_id, func.count()).group_by(exams.c.course_id)).all())
    attempt_counts = dict(db.execute(select(handed_in.c.course_id, func.count()).group_by(handed_in.c.course_id)).all())
    return [
        {"subject": name, "exams": exam_counts.get(cid, 0), "attempts": attempt_counts.get(cid, 0), "score_share": scores.get(cid)}
        for cid, name in db.execute(select(Course.id, Course.name).where(Course.user_id == user_id).order_by(Course.name))
    ]


def progress(db: Session, user_id: uuid.UUID, subject: str | None) -> list[dict]:
    courses = [_course(db, user_id, subject)] if subject else db.scalars(
        select(Course).where(Course.user_id == user_id).order_by(Course.name)
    ).all()  # fmt: skip
    only = courses[0].id if subject else None
    scored = _scored(db, user_id, only)
    scores = _scores(scored)
    tasks, recent = defaultdict(lambda: defaultdict(list)), defaultdict(dict)
    for x in scored:
        exam, a, cid = x["exam"], x["attempt"], x["exam"].course_id
        for t in exam.tasks:
            pairs = [x["subtasks"][s.key] for s in t.subtasks if s.key in x["subtasks"]]
            if pairs:
                tasks[cid][(exam.title, exam.id, t.position, _task_name(t))] += pairs
        if a.handed_in_at is not None:
            recent[cid][(a.handed_in_at, a.id)] = _sum(x["subtasks"].values())
    done = exists().where(Attempt.exam_id == Exam.id, Attempt.user_id == user_id, Attempt.status == "handed_in")
    unattempted = defaultdict(list)
    for eid, cid, title in db.execute(_practice_exams(user_id, only).add_columns(Exam.title).where(~done).order_by(Exam.title)):
        unattempted[cid].append({"exam_id": str(eid), "title": title})
    return [{
        "subject": c.name,
        "score_share": scores.get(c.id),
        "tasks": sorted(
            ({"exam": e, "task": t, "score_share": _share(*_sum(v))} for (e, _, _, t), v in sorted(tasks[c.id].items())),
            key=lambda t: (t["score_share"] is None, t["score_share"]),
        ),
        "recent": [{"handed_in_at": at.isoformat(), "score_share": _share(*v)}
                   for (at, _), v in sorted(recent[c.id].items(), key=lambda kv: kv[0][0], reverse=True)[:5]],
        "unattempted": unattempted[c.id],
    } for c in courses]  # fmt: skip


def latest_shares(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> dict[tuple[uuid.UUID, str], float | None]:
    """(exam id, subtask key) -> share in the latest attempt that had it (undated attempts last)."""
    last = {}
    undated = datetime.min.replace(tzinfo=UTC)
    for x in sorted(_scored(db, user_id, course_id), key=lambda x: x["attempt"].handed_in_at or undated):  # newer overwrite
        for key, (got, mx) in x["subtasks"].items():
            last[(x["exam"].id, key)] = _share(got, mx)
    return last


def _course_subtasks(user_id: uuid.UUID, course_id: uuid.UUID):
    """Exam, Task, Subtask rows of the course's practice exams, in reading order."""
    exams = _practice_exams(user_id, course_id).subquery()
    return (
        select(Exam, Task, Subtask)
        .join(exams, exams.c.id == Exam.id)
        .join(Task, Task.exam_id == Exam.id)
        .join(Subtask, Subtask.task_id == Task.id)
        .order_by(Exam.title, Exam.id, Task.position, Subtask.position)
    )


def weak_refs(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, below: float, limit: int) -> list[str]:
    """Wire ids of the course's subtasks whose latest share is below `below` (never the unattempted), in reading order."""
    last = latest_shares(db, user_id, course_id)
    weak = []
    for exam, _, sub in db.execute(_course_subtasks(user_id, course_id)):
        share = last.get((exam.id, sub.key))
        if share is not None and share < below:
            weak.append(f"{exam.id}/{sub.key}")
    return weak[:limit]


def find_tasks(db: Session, user_id: uuid.UUID, subject: str, query: str | None, filter: str | None, limit: int | None = 20) -> list[dict]:
    below = None
    if filter and filter.startswith("scored_below:"):
        try:
            below = float(filter.removeprefix("scored_below:"))
        except ValueError:
            below = None
        if below is None or not 0 <= below <= 1:
            raise BadInput("scored_below takes a share between 0 and 1")
    elif filter not in (None, "unattempted", "has_solution"):
        raise BadInput('filter must be "unattempted", "scored_below:<0..1>" or "has_solution"')
    course = _course(db, user_id, subject)
    last = latest_shares(db, user_id, course.id)
    q = _course_subtasks(user_id, course.id)
    if query:
        like = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        # meaning first (closest first); the text match still catches subtasks the worker has not indexed yet
        similar = similar_subtasks(db, user_id, course.id, query)
        q = q.where(or_(Subtask.id.in_(similar), *(c.ilike(like, escape="\\") for c in (Subtask.text, Subtask.label, Task.title))))
        if similar:
            rank = case({sid: i for i, sid in enumerate(similar)}, value=Subtask.id, else_=len(similar))
            q = q.order_by(None).order_by(rank, Exam.title, Exam.id, Task.position, Subtask.position)
    attempts = select(Attempt.id).where(Attempt.user_id == user_id, Attempt.exam_id == Exam.id, Attempt.status == "handed_in")
    if filter == "unattempted":
        q = q.where(~exists(attempts.where(Task.key == any_(Attempt.included_task_ids))))
    elif filter == "has_solution":
        q = q.where(or_(
            Subtask.solution_text != "", func.cardinality(Subtask.mc_key) > 0, Exam.has_ink,
            exists(attempts.where(Attempt.solution_exam_id.is_not(None))),
        ))  # fmt: skip
    out = []
    for exam, task, sub in db.execute(q):
        mx = subtask_max(exam, sub)
        share = last.get((exam.id, sub.key))
        if below is not None and not (share is not None and share < below):
            continue
        out.append({
            "id": f"{exam.id}/{sub.key}", "exam": exam.title, "task": _task_name(task), "label": sub.label,
            "points": mx, "preview": sub.text if len(sub.text) <= 200 else sub.text[:200] + "…", "last_score_share": share,
        })  # fmt: skip
        if len(out) == limit:
            break
    return out


def _crops(exam_id: uuid.UUID, layer: str, regions: list[dict]) -> list[Path]:
    # names come from client-synced structures: only plain crop names that stay inside the exam's directory
    root = exam_dir(exam_id).resolve()
    paths = (exam_dir(exam_id) / layer / "crops" / r["image"] for r in regions if CROP_NAME.fullmatch(r.get("image") or ""))
    return [p for p in paths if p.is_file() and p.resolve().is_relative_to(root)]


def _applicable_context(task: Task, sub: Subtask) -> list[dict]:
    position = {s.key: s.position for s in task.subtasks}
    return [c for c in task.context if position.get(c.get("applies_from"), -1) <= sub.position]


def context_crops(db: Session, user_id: uuid.UUID, ref: str) -> list[Path]:
    """Crop files of the context blocks that apply to this subtask (blank layer)."""
    exam, task, sub = resolve(db, user_id, ref)
    return [p for c in _applicable_context(task, sub) for p in _crops(exam.id, "blank", c.get("regions") or [])]


def get_task(db: Session, user_id: uuid.UUID, ref: str, include_solution: bool) -> tuple[dict, list[Path]]:
    exam, task, sub = resolve(db, user_id, ref)
    context = [c["text"] for c in _applicable_context(task, sub) if c.get("text")]
    out = {
        "id": ref, "exam": exam.title, "task": _task_name(task), "task_context_text": "\n\n".join(context),
        "label": sub.label, "text": sub.text, "points": subtask_max(exam, sub), "mc_options": [o["text"] for o in sub.mc_options],
        "visual": any(r.get("visual") is not False for r in sub.regions),
    }  # fmt: skip
    order = [s.key for t in exam.tasks for s in t.subtasks]
    i = order.index(sub.key) + 1
    out["next"] = f"{exam.id}/{order[i]}" if i < len(order) else None
    paths = _crops(exam.id, "blank", sub.regions)
    if include_solution:
        sol = None if exam.has_ink else _solution_exam(db, user_id, exam.id)
        match = match_solution(from_rows(exam), from_rows(sol)).get(sub.key) if sol else None
        out["solution"] = {
            "text": sub.solution_text or (match.solution_text if match else ""),
            "mc_key": sub.mc_key or (match.mc_key if match else None),
        }
        if exam.has_ink:
            paths += _crops(exam.id, "ink", sub.regions)
        elif match:  # the solution's ink layer shows the ticked boxes; its blank layer has them removed
            paths += _crops(sol.id, "ink" if sol.has_ink else "blank", [r.model_dump() for r in match.regions])
    return out, paths


def my_history(db: Session, user_id: uuid.UUID, ref: str) -> list[dict]:
    exam, _, sub = resolve(db, user_id, ref)
    rows = db.scalars(
        select(Attempt)
        .where(Attempt.user_id == user_id, Attempt.exam_id == exam.id, Attempt.status == "handed_in")
        .where(or_(
            exists().where(Answer.attempt_id == Attempt.id, Answer.subtask_id == sub.id),
            exists().where(Grade.attempt_id == Attempt.id, Grade.subtask_id == sub.id),
        ))
        .order_by(Attempt.handed_in_at.desc())
        .options(selectinload(Attempt.answers), selectinload(Attempt.grades))
    )  # fmt: skip
    out = []
    for a in rows:
        answers = {x.version: x for x in a.answers if x.subtask_id == sub.id}
        answer = answers.get("over") or answers.get("main")
        grade = next((g for g in a.grades if g.subtask_id == sub.id), None)
        got = grade and (grade.over if grade.over is not None else grade.main)
        llm = (grade and grade.llm) or {}
        out.append({
            "attempt_id": str(a.id),
            "handed_in_at": a.handed_in_at.isoformat() if a.handed_in_at else None,
            "answer_text": "\n".join(p["text"] for p in answer.parts if p.get("text")) if answer else "",
            "points": None if got is None else float(got),
            "max": subtask_max(exam, sub),
            "comment": grade and grade.comment,
            "llm_feedback": (llm.get("over") or llm.get("main") or {}).get("feedback"),
        })  # fmt: skip
    return out


class PracticeResult(TypedDict):
    subtask_id: str
    answer: str
    points: float
    feedback: str
    ticks: NotRequired[list[int]]  # MC: the chosen options, 0-based indices into mc_options


def _answer(sub: Subtask, r: PracticeResult) -> AnswerWire:
    """The app's answer shape: ticked boxes for an MC subtask, typed text otherwise."""
    if not sub.mc_options:
        return AnswerWire(mode="type", parts=[{"text": r["answer"], "strokes": []}])
    ticks = r.get("ticks")
    if ticks is None:  # the answer may name an option exactly
        ticks = [i for i, o in enumerate(sub.mc_options) if o.get("text", "").strip().lower() == r["answer"].strip().lower()]
        if not ticks:
            raise BadInput(f"{sub.key} is multiple choice: pass ticks, 0-based indices into its mc_options ([] for no answer)")
    if not all(isinstance(t, int) and 0 <= t < len(sub.mc_options) for t in ticks):
        raise BadInput(f"ticks for {sub.key} must be 0-based indices into its {len(sub.mc_options)} mc_options")
    return AnswerWire(mode="type", parts=[], ticks=sorted(set(ticks)))


def record_practice(db: Session, user_id: uuid.UUID, results: list[PracticeResult]) -> dict:
    """Save graded answers to one task. Practice at the same exam within PRACTICE_SESSION of the last save joins that
    attempt, so a session is one handed-in attempt in the app; sync brings it to the user's devices."""
    if not 1 <= len(results) <= 20:
        raise BadInput("pass 1 to 20 results")
    rows = [resolve(db, user_id, r["subtask_id"]) for r in results]
    exam, task, _ = rows[0]
    if any(e.id != exam.id or t.id != task.id for e, t, _ in rows):
        raise BadInput("one task per call")
    if len({sub.id for _, _, sub in rows}) < len(rows):
        raise BadInput("each subtask once per call")
    if not all(math.isfinite(r["points"]) and r["points"] <= 1000 for r in results):  # Grade is Numeric(6, 2)
        raise BadInput("points must be a number, at most 1000")
    now = round(time.time() * 1000)
    graded = []
    for r, (_, _, sub) in zip(results, rows):
        mx = subtask_max(exam, sub)
        p = round(max(0.0, r["points"] if mx is None else min(r["points"], mx)), 2)
        clean = {k: r[k].replace("\x00", "") for k in ("answer", "feedback")}  # Postgres text and JSONB reject NUL
        graded.append((r | clean, sub.key, mx, p, _answer(sub, r | clean)))
    keys = subtask_keys(db, exam.id)
    current = db.scalar(
        select(Attempt)
        .where(Attempt.user_id == user_id, Attempt.exam_id == exam.id, PRACTICE, Attempt.status == "handed_in")
        .where(Attempt.edited_at > datetime.now(UTC) - PRACTICE_SESSION)
        .order_by(Attempt.edited_at.desc())
        .limit(1)
    )
    if current is None:
        sol = None if exam.has_ink else _solution_exam(db, user_id, exam.id)
        w = AttemptWire(
            id=uuid.uuid4(), exam_id=exam.id, solution_exam_id=sol and sol.id, status="handed_in", fresh=False,
            started_at=now, time_limit_ms=0, included_task_ids=[], attendance_at=None, attendance_done=False,
            mc_rule=exam.mc_rule or {"kind": "all_or_nothing"}, extended=False, snapshot=None, edited_at=now,
            handed_in_at=now, answers={}, time={}, grades={},
        )  # fmt: skip
    else:
        w = read_attempt(current, {v: k for k, v in keys.items()})
    order = [t.key for t in exam.tasks]
    w.included_task_ids = sorted({*w.included_task_ids, task.key}, key=order.index)
    for r, k, _, p, answer in graded:  # practicing a subtask again in the same session replaces the earlier answer
        w.answers[k] = answer
        w.time[k] = TimeWire(main=0, over=0)
        w.grades[k] = GradeWire(main=p, comment=r["feedback"])
    w.handed_in_at = w.graded_at = w.edited_at = now
    write_attempt(db, user_id, w, keys)
    db.commit()
    return {
        "attempt_id": str(w.id),
        "points": [{"subtask_id": r["subtask_id"], "points": p, "max": mx} for r, _, mx, p, _ in graded],
    }


def set_points(db: Session, user_id: uuid.UUID, ref: str, points: float) -> dict:
    if not 0 < points <= 1000:
        raise BadInput("points must be above 0 and at most 1000")
    exam, _, sub = resolve(db, user_id, ref)
    exam.point_overrides = {**(exam.point_overrides or {}), sub.key: points}  # a new dict, so the JSONB change is saved
    exam.edited_at = func.now()
    db.commit()
    return {"subtask_id": ref, "points": points}
