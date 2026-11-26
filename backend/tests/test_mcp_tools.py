import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from mcp import Client
from sqlalchemy import select
from test_auth import signed_in
from test_db import SAMPLE
from test_sync import full

from app.core.storage import exam_dir
from app.db.attempts import subtask_keys, write_attempt
from app.db.exams import course_id, to_rows
from app.db.models import Answer, Attempt, Exam, Grade, Subtask, User
from app.db.sync import AnswerWire, AttemptWire, GradeWire, ms
from app.mcp import tools
from app.mcp.auth import current_user_id
from app.mcp.server import mcp
from app.pipeline.models import McRule

T1 = SAMPLE.tasks[0]
T2 = T1.model_copy(update={"id": "A2", "number": "2", "title": "Routing",
                           "subtasks": [s.model_copy(update={"id": "A2" + s.id[-1]}) for s in T1.subtasks]})  # fmt: skip
TWO = SAMPLE.model_copy(update={"is_solution": False, "tasks": [T1, T2]})
PRACTICE = SAMPLE.model_copy(update={"is_solution": False})
NOW = datetime(2026, 11, 1, tzinfo=UTC)


def crop(exam, layer, name="a.png"):
    path = exam_dir(exam) / layer / "crops" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    return path


def attempt(db, user, exam, grades, at=NOW, **kw):
    w = AttemptWire(
        id=uuid.uuid4(), exam_id=exam, status="handed_in", fresh=True, started_at=ms(at), time_limit_ms=1,
        included_task_ids=kw.pop("included_task_ids", ["A1", "A2"]), attendance_at=None, attendance_done=False, mc_rule=McRule(kind="per_tick"),
        extended=False, answers={k: AnswerWire(mode="type", parts=[{"text": f"ans {k}"}, {"text": "more"}]) for k in grades},
        snapshot=None, handed_in_at=ms(at), graded_at=ms(at), time={}, grades={k: GradeWire(main=v, comment="ok") for k, v in grades.items()}, **kw,
    )  # fmt: skip
    write_attempt(db, user, w, subtask_keys(db, exam))
    db.flush()
    return w.id


@pytest.fixture
def seed(db):
    """User a: E1 (two tasks, one graded attempt: A1 1/4, A2 4/4), E2 (no attempt, has ink), a hidden exam
    and a solution exam S. User b: an exam of their own."""
    a, b = uuid.uuid4(), uuid.uuid4()
    db.add_all([User(id=a), User(id=b)])
    db.flush()
    cid = course_id(db, a, "GRNVS")
    e1, e2, hidden, sol, other = (uuid.uuid4() for _ in range(5))
    two = {"A1a": 2, "A1b": 2, "A2a": 2, "A2b": 2}
    db.add(to_rows(e1, TWO, title="Endterm 2024", user_id=a, course_id=cid, point_overrides=two))
    db.add(to_rows(e2, PRACTICE, title="Retake 2024", user_id=a, course_id=cid, has_ink=True))
    db.add(to_rows(hidden, PRACTICE, title="Hidden", user_id=a, course_id=cid, hidden=True))
    db.add(to_rows(sol, SAMPLE, title="Endterm 2024 solution", user_id=a, course_id=cid, solution_for=e1))
    db.add(to_rows(other, PRACTICE, title="B's exam", user_id=b, course_id=course_id(db, b, "Other")))
    db.flush()
    att = attempt(db, a, e1, {"A1a": 0, "A1b": 1, "A2a": 2, "A2b": 2})
    for e in (e1, e2, sol):
        crop(e, "blank")
    crop(e2, "ink")
    return dict(a=a, b=b, e1=e1, e2=e2, hidden=hidden, sol=sol, other=other, attempt=att)


def ids(rows):
    return {r["id"] for r in rows}


def test_resolve_rejects_other_users_and_garbage(db, seed):
    exam, task, sub = tools.resolve(db, seed["a"], f"{seed['e1']}/A2b")
    assert (exam.id, task.key, sub.key) == (seed["e1"], "A2", "A2b")
    for ref in (f"{seed['other']}/A1a", "nope", f"{seed['e1']}/ZZ"):
        with pytest.raises(tools.NotFound, match="^not found$"):
            tools.resolve(db, seed["a"], ref)


def test_progress_weakest_first_and_unattempted(db, seed):
    [p] = tools.progress(db, seed["a"], "grnvs")
    assert p["subject"] == "GRNVS" and p["score_share"] == 0.625
    assert [(t["task"], t["score_share"]) for t in p["tasks"]] == [("Basics", 0.25), ("Routing", 1.0)]
    assert p["tasks"][0]["exam"] == "Endterm 2024"
    assert p["recent"] == [{"handed_in_at": NOW.isoformat(), "score_share": 0.625}]
    assert p["unattempted"] == [{"exam_id": str(seed["e2"]), "title": "Retake 2024"}]
    assert tools.progress(db, seed["a"], None) == [p]
    with pytest.raises(tools.NotFound):
        tools.progress(db, seed["a"], "Other")


def test_find_tasks_filters(db, seed):
    e1, e2 = seed["e1"], seed["e2"]
    rows = tools.find_tasks(db, seed["a"], "GRNVS", None, None)
    assert [r["id"] for r in rows] == [f"{e1}/A1a", f"{e1}/A1b", f"{e1}/A2a", f"{e1}/A2b", f"{e2}/A1a", f"{e2}/A1b"]
    assert rows[0] | {"id": None} == {"id": None, "exam": "Endterm 2024", "task": "Basics", "label": "a)*", "points": 2.0,
                                      "preview": "question", "last_score_share": 0.0}  # fmt: skip
    assert ids(tools.find_tasks(db, seed["a"], "GRNVS", None, "unattempted")) == {f"{e2}/A1a", f"{e2}/A1b"}
    assert ids(tools.find_tasks(db, seed["a"], "GRNVS", None, "scored_below:0.5")) == {f"{e1}/A1a"}
    assert ids(tools.find_tasks(db, seed["a"], "GRNVS", None, "has_solution")) == {f"{e1}/A1a", f"{e1}/A2a", f"{e2}/A1a", f"{e2}/A1b"}
    assert ids(tools.find_tasks(db, seed["a"], "GRNVS", "routing", None)) == {f"{e1}/A2a", f"{e1}/A2b"}
    assert tools.find_tasks(db, seed["a"], "GRNVS", "%", None) == []
    for bad in ("scored_below:2", "scored_below:abc"):
        with pytest.raises(tools.BadInput, match="^scored_below takes a share between 0 and 1$"):
            tools.find_tasks(db, seed["a"], "GRNVS", None, bad)
    with pytest.raises(tools.BadInput):
        tools.find_tasks(db, seed["a"], "GRNVS", None, "bogus")
    with pytest.raises(tools.NotFound):
        tools.find_tasks(db, seed["a"], "Other", None, None)


def test_find_tasks_has_solution_via_attempt(db, seed):
    db.get(Attempt, seed["attempt"]).solution_exam_id = seed["sol"]
    db.flush()
    rows = tools.find_tasks(db, seed["a"], "GRNVS", None, "has_solution")
    assert {f"{seed['e1']}/A1b", f"{seed['e1']}/A2b"} <= ids(rows)


def test_get_task_hides_solution_unless_asked(db, seed):
    ref = f"{seed['e2']}/A1a"
    task, paths = tools.get_task(db, seed["a"], ref, False)
    assert "solution" not in task and paths == [exam_dir(seed["e2"]) / "blank/crops/a.png"]
    assert task | {"id": None} == {"id": None, "exam": "Retake 2024", "task": "Basics", "task_context_text": "stem",
                                   "label": "a)*", "text": "question", "points": 0.5, "mc_options": ["yes", "no"],
                                   "next": f"{seed['e2']}/A1b", "visual": True}  # fmt: skip
    task, paths = tools.get_task(db, seed["a"], ref, True)
    assert task["solution"] == {"text": "answer", "mc_key": [1]}
    assert paths == [exam_dir(seed["e2"]) / "blank/crops/a.png", exam_dir(seed["e2"]) / "ink/crops/a.png"]


def test_get_task_solution_crops_from_attempts_solution_exam(db, seed):
    ref = f"{seed['e1']}/A1a"
    assert tools.get_task(db, seed["a"], ref, True)[1] == [exam_dir(seed["e1"]) / "blank/crops/a.png"]
    db.get(Attempt, seed["attempt"]).solution_exam_id = seed["sol"]
    db.flush()
    assert tools.get_task(db, seed["a"], ref, True)[1][1:] == [exam_dir(seed["sol"]) / "blank/crops/a.png"]


def test_context_crops_for_applicable_context_only(db, seed):
    ctx = crop(seed["e1"], "blank", "ctx.png")
    _, task, _ = tools.resolve(db, seed["a"], f"{seed['e1']}/A1a")
    later = {"id": "later", "applies_from": "A1b", "regions": [{"page": 0, "bbox": {}, "image": "later.png"}], "text": ""}
    gone = {"id": "gone", "applies_from": None, "regions": [{"page": 0, "bbox": {}, "image": "gone.png"}], "text": ""}
    crop(seed["e1"], "blank", "later.png")
    task.context = [*task.context, later, gone]
    db.flush()
    assert tools.context_crops(db, seed["a"], f"{seed['e1']}/A1a") == [ctx]
    assert tools.context_crops(db, seed["a"], f"{seed['e1']}/A1b") == [ctx, exam_dir(seed["e1"]) / "blank/crops/later.png"]


def test_get_task_skips_crop_names_outside_the_exam(db, seed):
    planted = crop(seed["e2"], "blank", "../x.png")  # exam_dir/blank/x.png, a real file one level up
    outside = crop(seed["sol"], "blank")
    sub = tools.resolve(db, seed["a"], f"{seed['e2']}/A1a")[2]
    sub.regions = [{**sub.regions[0], "image": "../x.png"}, {**sub.regions[0], "image": str(outside)}]
    db.flush()
    _, paths = tools.get_task(db, seed["a"], f"{seed['e2']}/A1a", True)
    assert planted.is_file() and outside.is_file() and paths == []


def test_subtask_max_null_override_falls_back(db, seed):
    exam, _, sub = tools.resolve(db, seed["a"], f"{seed['e2']}/A1a")
    exam.point_overrides = {"A1a": None}
    assert tools.subtask_max(exam, sub) == 0.5


def test_progress_keeps_same_titled_exams_apart(db, seed):
    db.get(Exam, seed["e2"]).title = "Endterm 2024"
    attempt(db, seed["a"], seed["e2"], {"A1a": 0.5})
    [p] = tools.progress(db, seed["a"], "GRNVS")
    assert sorted(t["score_share"] for t in p["tasks"]) == [0.25, 1.0, 1.0]


def test_progress_skips_undated_attempts_in_recent(db, seed):
    undated = attempt(db, seed["a"], seed["e1"], {"A1a": 2}, at=NOW + timedelta(days=1))
    db.get(Attempt, undated).handed_in_at = None
    db.flush()
    [p] = tools.progress(db, seed["a"], "GRNVS")
    assert p["recent"] == [{"handed_in_at": NOW.isoformat(), "score_share": 0.625}]


def test_last_score_is_the_newest_dated_attempt(db, seed):
    attempt(db, seed["a"], seed["e1"], {"A1a": 2, "A1b": 2}, at=NOW + timedelta(days=1), included_task_ids=["A1"])
    undated = attempt(db, seed["a"], seed["e1"], {"A1a": 0}, at=NOW + timedelta(days=2), included_task_ids=["A1"])
    db.get(Attempt, undated).handed_in_at = None
    db.flush()
    assert ids(tools.find_tasks(db, seed["a"], "GRNVS", None, "scored_below:0.5")) == set()


def test_ungraded_subtask_of_an_included_task_scores_zero(db, seed):
    attempt(db, seed["a"], seed["e1"], {"A1a": 2}, at=NOW + timedelta(days=1), included_task_ids=["A1"])
    assert ids(tools.find_tasks(db, seed["a"], "GRNVS", None, "scored_below:0.5")) == {f"{seed['e1']}/A1b"}


def test_list_subjects_and_progress_share_the_score(db, seed):
    attempt(db, seed["a"], seed["e2"], {"A1a": 0.5, "A1b": 1})
    [s] = tools.list_subjects(db, seed["a"])
    [p] = tools.progress(db, seed["a"], "GRNVS")
    assert s["score_share"] == p["score_share"] == 0.765  # like the app: points of subtasks without a known max still count


def test_my_history_newest_first(db, seed):
    later = attempt(db, seed["a"], seed["e1"], {"A1a": 2}, at=NOW + timedelta(days=1))
    attempt(db, seed["a"], seed["e1"], {"A2a": 2}, at=NOW + timedelta(days=2))  # doesn't contain A1a
    rows = tools.my_history(db, seed["a"], f"{seed['e1']}/A1a")
    assert [r["attempt_id"] for r in rows] == [str(later), str(seed["attempt"])]
    assert rows[1] == {"attempt_id": str(seed["attempt"]), "handed_in_at": NOW.isoformat(), "answer_text": "ans A1a\nmore",
                       "points": 0.0, "max": 2.0, "comment": "ok", "llm_feedback": None}  # fmt: skip
    with pytest.raises(tools.NotFound):
        tools.my_history(db, seed["b"], f"{seed['e1']}/A1a")


def practice(ref, points, answer="my answer", feedback="close", ticks=(1,)):
    return {"subtask_id": ref, "answer": answer, "points": points, "feedback": feedback, "ticks": list(ticks)}  # ticks: MC only


def test_record_practice_writes_synced_attempt(db, monkeypatch):
    user = signed_in(monkeypatch, uuid.uuid4().hex)
    e = uuid.uuid4()
    assert user.put(f"/api/exams/{e}", json=full(e, pointOverrides={"A1a": 2})).status_code == 204
    uid = uuid.UUID(user.get("/api/me").json()["user"]["id"])
    out = tools.record_practice(db, uid, [practice(f"{e}/A1a", 99)])
    assert out["points"] == [{"subtask_id": f"{e}/A1a", "points": 2.0, "max": 2.0}]
    assert float(db.scalar(select(Grade.main).where(Grade.attempt_id == uuid.UUID(out["attempt_id"])))) == 2
    [a] = user.get("/api/sync").json()["attempts"]
    assert a["id"] == out["attempt_id"] and a["includedTaskIds"] == ["A1"] and a["status"] == "handed_in"
    assert a["grades"] == {"A1a": {"main": 2.0, "comment": "close"}}
    assert a["answers"]["A1a"]["ticks"] == [1] and a["answers"]["A1a"]["parts"] == []  # MC: the ticked box


def test_record_practice_clamps_negative_and_unknown_max(db, seed):
    e2 = seed["e2"]
    out = tools.record_practice(db, seed["a"], [practice(f"{e2}/A1a", -3), practice(f"{e2}/A1b", 5)])
    assert out["points"] == [{"subtask_id": f"{e2}/A1a", "points": 0.0, "max": 0.5},
                             {"subtask_id": f"{e2}/A1b", "points": 5.0, "max": None}]  # fmt: skip
    assert db.get(Attempt, uuid.UUID(out["attempt_id"])).mc_rule["kind"] == "per_tick"  # the exam's rule


def test_record_practice_one_task_per_call(db, seed):
    e1, e2 = seed["e1"], seed["e2"]
    for refs in ([f"{e1}/A1a", f"{e1}/A2a"], [f"{e1}/A1a", f"{e2}/A1a"]):
        with pytest.raises(tools.BadInput, match="^one task per call$"):
            tools.record_practice(db, seed["a"], [practice(r, 1) for r in refs])
    for results in ([], [practice(f"{e1}/A1a", 1)] * 21):
        with pytest.raises(tools.BadInput):
            tools.record_practice(db, seed["a"], results)


def test_record_practice_rejects_huge_points_and_repeated_subtasks(db, seed):
    ref = f"{seed['e2']}/A1b"
    with pytest.raises(tools.BadInput, match="^points must be a number, at most 1000$"):
        tools.record_practice(db, seed["a"], [practice(ref, 5000)])
    with pytest.raises(tools.BadInput, match="^each subtask once per call$"):
        tools.record_practice(db, seed["a"], [practice(ref, 1), practice(ref, 1)])


def test_record_practice_rounds_points_and_strips_nul(db, seed):
    ref = f"{seed['e2']}/A1b"
    out = tools.record_practice(db, seed["a"], [practice(ref, 1.23456, answer="a\x00b", feedback="ok\x00")])
    assert out["points"] == [{"subtask_id": ref, "points": 1.23, "max": None}]
    aid = uuid.UUID(out["attempt_id"])
    grade = db.scalar(select(Grade).where(Grade.attempt_id == aid))
    assert float(grade.main) == 1.23 and grade.comment == "ok"
    assert db.scalar(select(Answer.parts).where(Answer.attempt_id == aid)) == [{"text": "ab", "strokes": []}]


def test_record_practice_foreign_subtask_not_found(db, seed):
    with pytest.raises(tools.NotFound):
        tools.record_practice(db, seed["b"], [practice(f"{seed['e1']}/A1a", 1)])


def test_set_points_overrides_and_bumps_edited_at(db, seed):
    ref = f"{seed['e1']}/A1a"
    before = db.get(Exam, seed["e1"]).edited_at
    assert tools.set_points(db, seed["a"], ref, 3) == {"subtask_id": ref, "points": 3}
    exam = db.get(Exam, seed["e1"])
    db.refresh(exam)
    assert exam.edited_at > before and exam.point_overrides == {"A1a": 3, "A1b": 2, "A2a": 2, "A2b": 2}
    assert tools.find_tasks(db, seed["a"], "GRNVS", None, None)[0]["points"] == 3
    for bad in (0, 5000):
        with pytest.raises(tools.BadInput):
            tools.set_points(db, seed["a"], ref, bad)
    with pytest.raises(tools.NotFound):
        tools.set_points(db, seed["b"], ref, 3)


@pytest.fixture
def committed(db, seed):
    db.commit()  # the server's own sessions must see the seed
    return seed


async def call(user, name, args):
    token = current_user_id.set(user)
    try:
        async with Client(mcp) as c:
            return await c.call_tool(name, args)
    finally:
        current_user_id.reset(token)


@pytest.mark.anyio
async def test_get_task_over_mcp_returns_images(committed):
    r = await call(committed["a"], "get_task", {"ref": f"{committed['e2']}/A1a"})
    assert not r.is_error
    assert [c.type for c in r.content] == ["text", "image"]
    assert json.loads(r.content[0].text)["label"] == "a)*"


@pytest.mark.anyio
async def test_tools_over_mcp_are_bound_to_the_user(committed):
    a, b = committed["a"], committed["b"]
    r = await call(a, "progress", {})
    assert [p["subject"] for p in r.structured_content["result"]] == ["GRNVS"]
    r = await call(b, "progress", {})
    assert [p["subject"] for p in r.structured_content["result"]] == ["Other"]
    r = await call(b, "get_task", {"ref": f"{committed['e1']}/A1a"})
    assert r.is_error and r.content[0].text.endswith("not found")
    r = await call(b, "find_tasks", {"subject": "GRNVS"})
    assert r.is_error and r.content[0].text.endswith("not found")
    r = await call(a, "find_tasks", {"subject": "GRNVS", "filter": "scored_below:abc"})
    assert r.is_error and r.content[0].text.endswith("scored_below takes a share between 0 and 1")


@pytest.mark.anyio
async def test_record_practice_over_mcp(committed):
    ref = f"{committed['e2']}/A1a"
    r = await call(committed["a"], "record_practice", {"results": [practice(ref, 0.5)]})
    assert not r.is_error and json.loads(r.content[0].text)["points"] == [{"subtask_id": ref, "points": 0.5, "max": 0.5}]
    r = await call(committed["a"], "record_practice", {"results": [practice(ref, 5000)]})
    assert r.is_error and r.content[0].text.endswith("points must be a number, at most 1000")


def unkeyed():
    """PRACTICE without its own MC key or solution text, like a question sheet."""
    t = PRACTICE.tasks[0]
    subs = [s.model_copy(update={"mc_key": None, "solution_text": ""}) for s in t.subtasks]
    return PRACTICE.model_copy(update={"tasks": [t.model_copy(update={"subtasks": subs})]})


def test_solution_exams_key_scores_ticks_and_reaches_get_task(db, seed):
    a, sol, q = seed["a"], seed["sol"], uuid.uuid4()
    db.add(to_rows(q, unkeyed(), title="Midterm", user_id=a, course_id=db.get(Exam, seed["e1"]).course_id))
    db.get(Exam, sol).has_ink = True
    db.flush()
    w = AttemptWire(
        id=uuid.uuid4(), exam_id=q, solution_exam_id=sol, status="handed_in", fresh=True, started_at=ms(NOW), time_limit_ms=1,
        included_task_ids=["A1"], attendance_at=None, attendance_done=False, mc_rule=McRule(kind="all_or_nothing"),
        extended=False, answers={"A1a": AnswerWire(mode="type", parts=[], ticks=[1])}, snapshot=None,
        handed_in_at=ms(NOW), graded_at=ms(NOW), time={}, grades={},
    )  # fmt: skip
    write_attempt(db, a, w, subtask_keys(db, q))
    db.flush()
    rows = {r["id"]: r for r in tools.find_tasks(db, a, "GRNVS", None, None)}
    assert rows[f"{q}/A1a"]["last_score_share"] == 1.0  # ticked the solution's key, no hand grade
    crop(sol, "ink")
    task, paths = tools.get_task(db, a, f"{q}/A1a", True)
    assert task["solution"] == {"text": "answer", "mc_key": [1]}
    assert paths == [exam_dir(sol) / "ink/crops/a.png"]  # the question exam has no crop files here


def test_record_practice_joins_the_session_attempt(db, seed):
    a, e1 = seed["a"], seed["e1"]
    db.get(Attempt, seed["attempt"]).solution_exam_id = seed["sol"]
    db.flush()
    first = tools.record_practice(db, a, [practice(f"{e1}/A2a", 1)])["attempt_id"]
    assert tools.record_practice(db, a, [practice(f"{e1}/A1a", 2), practice(f"{e1}/A1b", 0)])["attempt_id"] == first
    assert tools.record_practice(db, a, [practice(f"{e1}/A2a", 2)])["attempt_id"] == first  # practiced again: replaces
    db.expire_all()
    row = db.get(Attempt, uuid.UUID(first))
    assert row.included_task_ids == ["A1", "A2"] and row.solution_exam_id == seed["sol"]
    grades = dict(db.execute(select(Subtask.key, Grade.main).join(Subtask, Subtask.id == Grade.subtask_id).where(Grade.attempt_id == row.id)).all())
    assert {k: float(v) for k, v in grades.items()} == {"A1a": 2, "A1b": 0, "A2a": 2}
    row.edited_at = datetime.now(UTC) - timedelta(hours=4)  # session over
    db.flush()
    assert tools.record_practice(db, a, [practice(f"{e1}/A1a", 1)])["attempt_id"] != first


def test_practice_attempt_scores_only_what_was_practiced(db, seed):
    tools.record_practice(db, seed["a"], [practice(f"{seed['e1']}/A1b", 2)])
    [p] = tools.progress(db, seed["a"], "GRNVS")
    assert p["recent"][0]["score_share"] == 1.0  # A1a, not practiced, does not count as 0


def test_record_practice_mc_ticks(db, seed):
    a, ref = seed["a"], f"{seed['e2']}/A1a"  # MC: options "yes", "no"
    out = tools.record_practice(db, a, [practice(ref, 0, answer="no idea", ticks=())])  # nothing ticked
    [answer] = db.scalars(select(Answer).where(Answer.attempt_id == uuid.UUID(out["attempt_id"]))).all()
    assert answer.ticks == []  # "I don't know"
    by_text = {"subtask_id": ref, "answer": " no ", "points": 0.5, "feedback": "ok"}  # no ticks: the option named exactly
    out = tools.record_practice(db, a, [by_text])
    [answer] = db.scalars(select(Answer).where(Answer.attempt_id == uuid.UUID(out["attempt_id"]))).all()
    assert answer.ticks == [1] and answer.parts == []
    with pytest.raises(tools.BadInput, match="pass ticks"):
        tools.record_practice(db, a, [by_text | {"answer": "probably no"}])
    with pytest.raises(tools.BadInput, match="0-based indices"):
        tools.record_practice(db, a, [practice(ref, 0.5, ticks=(2,))])


def test_scored_loads_exams_in_one_go(db, seed):
    from sqlalchemy import event

    attempt(db, seed["a"], seed["e1"], {"A1a": 1}, solution_exam_id=seed["sol"])
    db.expire_all()
    n = []
    listener = lambda *a: n.append(1)
    event.listen(db.get_bind(), "before_cursor_execute", listener)
    try:
        tools._scored(db, seed["a"])
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listener)
    assert len(n) <= 11  # was 12: tasks and subtasks of the exam and its solution are loaded together, not lazily per task


def test_weak_refs_below_threshold(db, seed):
    e1, cid = seed["e1"], course_id(db, seed["a"], "GRNVS")
    assert tools.weak_refs(db, seed["a"], cid, 0.6, 10) == [f"{e1}/A1a", f"{e1}/A1b"]


def test_weak_refs_threshold_is_strict(db, seed):
    e1, cid = seed["e1"], course_id(db, seed["a"], "GRNVS")
    assert tools.weak_refs(db, seed["a"], cid, 0.5, 10) == [f"{e1}/A1a"]


def test_weak_refs_skip_unattempted_and_cap(db, seed):
    cid = course_id(db, seed["a"], "GRNVS")
    refs = tools.weak_refs(db, seed["a"], cid, 1.0, 10)
    assert refs and not any(r.startswith(str(seed["e2"])) for r in refs)
    assert len(tools.weak_refs(db, seed["a"], cid, 1.0, 1)) == 1
