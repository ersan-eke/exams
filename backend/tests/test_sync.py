import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from test_auth import signed_in
from test_db import SAMPLE

from app.api.routes import read_capped
from app.core.storage import exam_dir
from app.db.attempts import read_attempt, subtask_keys
from app.db.exams import to_rows
from app.db.models import Answer, Attempt, Course, Exam, Grade
from app.db.sync import AttemptWire
from main import app

png = b"\x89PNG\r\n\x1a\n" + b"x"
b64 = lambda b: base64.b64encode(b).decode()


def meta(id, **kw):
    return {"id": str(id), "title": "Endterm", "hasInk": False, "createdAt": 1000, "editedAt": 1000, **kw}


def full(id, **kw):
    return meta(id, structure=SAMPLE.model_dump(mode="json"), images={"A1a.png": b64(png)}, **kw)


@pytest.fixture
def user(monkeypatch):
    return signed_in(monkeypatch, uuid.uuid4().hex)


def test_sync_routes_need_sign_in():
    i = uuid.uuid4()
    assert TestClient(app).put(f"/api/exams/{i}", json=meta(i)).status_code == 401
    assert TestClient(app).put(f"/api/attempts/{i}", json={}).status_code == 401
    assert TestClient(app).get("/api/sync").status_code == 401


def test_put_exam_creates_rows_and_crops(db, user):
    i = uuid.uuid4()
    assert user.put(f"/api/exams/{i}", json=full(i, subject="GRNVS")).status_code == 204
    got = user.get(f"/api/exams/{i}").json()
    assert got["exam"] == SAMPLE.model_dump(mode="json") and got["images"]["A1a.png"] == b64(png)
    exam = db.get(Exam, i)
    assert exam.user_id == uuid.UUID(user.get("/api/me").json()["user"]["id"])
    assert db.get(Course, exam.course_id).name == "GRNVS"


def test_put_exam_without_content_is_409(user):
    i = uuid.uuid4()
    r = user.put(f"/api/exams/{i}", json=meta(i))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "need_content"
    j = uuid.uuid4()
    assert user.put(f"/api/exams/{j}", json=full(j, hasInk=True)).status_code == 409
    k = uuid.uuid4()
    assert user.put(f"/api/exams/{k}", json=full(k) | {"images": None}).status_code == 409
    assert user.put(f"/api/exams/{k}", json=full(k) | {"images": {}}).status_code == 204
    m = uuid.uuid4()  # an ink exam whose ink has no crops is still complete
    assert user.put(f"/api/exams/{m}", json=full(m, hasInk=True, solutionImages={})).status_code == 204


def test_put_exam_updates_metadata_only(user):
    i = uuid.uuid4()
    user.put(f"/api/exams/{i}", json=full(i))
    other = SAMPLE.model_copy(update={"source": "other.pdf"}).model_dump(mode="json")
    body = full(i, title="New", pointOverrides={"A1a": 3}, editedAt=2000) | {"structure": other}
    assert user.put(f"/api/exams/{i}", json=body).status_code == 204
    got = user.get(f"/api/exams/{i}").json()["exam"]
    assert got["source"] == SAMPLE.source


def test_put_exam_metadata_columns(db, user):
    i = uuid.uuid4()
    user.put(f"/api/exams/{i}", json=full(i))
    user.put(f"/api/exams/{i}", json=meta(i, title="New", pointOverrides={"A1a": 3}, editedAt=2000))
    db.expire_all()
    e = db.get(Exam, i)
    assert (e.title, e.point_overrides) == ("New", {"A1a": 3})


def test_put_exam_subject_null_keeps_course_empty_clears(db, user):
    i = uuid.uuid4()
    user.put(f"/api/exams/{i}", json=full(i, subject="GRNVS"))
    course = db.get(Exam, i).course_id
    assert user.put(f"/api/exams/{i}", json=meta(i, editedAt=2000)).status_code == 204
    db.expire_all()
    assert db.get(Exam, i).course_id == course
    assert user.put(f"/api/exams/{i}", json=meta(i, editedAt=3000, subject=None)).status_code == 204
    db.expire_all()
    assert db.get(Exam, i).course_id == course
    assert user.put(f"/api/exams/{i}", json=meta(i, editedAt=4000, subject="")).status_code == 204
    db.expire_all()
    assert db.get(Exam, i).course_id is None


def test_put_exam_ignores_stale_edit(db, user):
    i = uuid.uuid4()
    user.put(f"/api/exams/{i}", json=full(i, editedAt=2000))
    before = db.scalar(select(func.count()).select_from(Course))
    assert user.put(f"/api/exams/{i}", json=meta(i, editedAt=1000, title="old", subject="NEWCOURSE")).status_code == 204
    db.expire_all()
    assert db.get(Exam, i).title == "Endterm"
    assert db.scalar(select(func.count()).select_from(Course)) == before


def test_put_exam_first_push_beats_worker_made_row(db, user):
    i = uuid.uuid4()
    db.add(to_rows(i, SAMPLE, title="Worker"))  # no edited_at, like the worker
    db.commit()
    assert user.put(f"/api/exams/{i}", json=meta(i, editedAt=0, title="Mine")).status_code == 204
    db.expire_all()
    assert db.get(Exam, i).title == "Mine"


def test_put_exam_claims_anonymous_upload(db, user):
    i = uuid.uuid4()
    db.add(to_rows(i, SAMPLE, title="Anon"))
    db.commit()
    assert user.put(f"/api/exams/{i}", json=meta(i, editedAt=2000)).status_code == 204
    assert user.get(f"/api/exams/{i}").status_code == 200
    assert TestClient(app).get(f"/api/exams/{i}").status_code == 404


def test_put_exam_of_other_user_is_404(db, user, monkeypatch):
    i = uuid.uuid4()
    user.put(f"/api/exams/{i}", json=full(i))
    other = signed_in(monkeypatch, uuid.uuid4().hex)
    assert other.put(f"/api/exams/{i}", json=meta(i, editedAt=9000)).status_code == 404


@pytest.mark.parametrize("name,data", [("../x.png", png), (".x.png", png), ("a.jpg", png), ("a.png", b"nope")])
def test_put_exam_rejects_bad_crops(user, name, data):
    i = uuid.uuid4()
    r = user.put(f"/api/exams/{i}", json=full(i) | {"images": {"A1a.png": b64(png), name: b64(data)}})
    assert r.status_code == 422 and not exam_dir(i).exists()


def test_put_exam_body_cap(user, monkeypatch):
    monkeypatch.setattr("app.api.sync.MAX_SYNC_BYTES", 1000)
    i = uuid.uuid4()
    assert user.put(f"/api/exams/{i}", json=full(i, title="x" * 2000)).status_code == 413


@pytest.mark.parametrize("kind", ["exams", "attempts"])
def test_put_writes_after_the_body_arrives(db, user, exam, monkeypatch, kind):
    """updated_at is the write's time, not the time the auth query opened the transaction."""
    import asyncio

    from app.api import sync
    from app.db.session import SessionLocal

    marks = []

    async def slow(request, limit):
        raw = await read_capped(request, limit)
        with SessionLocal() as s:
            marks.append(s.scalar(select(func.now())))
        await asyncio.sleep(1.1)
        return raw

    monkeypatch.setattr(sync, "read_capped", slow)
    i = uuid.uuid4()
    body = meta(exam, editedAt=2000) if kind == "exams" else attempt_body(i, exam)
    rid = exam if kind == "exams" else i
    assert user.put(f"/api/{kind}/{rid}", json=body).status_code == 204
    db.expire_all()
    assert db.get(Exam if kind == "exams" else Attempt, rid).updated_at > marks[0]


def ans(text="hi"):
    return {"mode": "type", "parts": [{"text": text, "strokes": []}], "done": False, "ticks": [1]}


def attempt_body(id, exam_id, **kw):
    return {
        "id": str(id), "examId": str(exam_id), "solutionExamId": None, "status": "handed_in", "fresh": True,
        "startedAt": 5000, "timeLimitMs": 60000, "includedTaskIds": ["A1"], "attendanceAt": None,
        "attendanceDone": False, "mcRule": {"kind": "all_or_nothing"}, "extended": False,
        "answers": {"A1a": ans()}, "snapshot": None, "handedInAt": 9000,
        "time": {"A1a": {"main": 10, "over": 0}}, "grades": {}, "gradedAt": None, "editedAt": 1000,
    } | kw  # fmt: skip


@pytest.fixture
def exam(user):
    i = uuid.uuid4()
    assert user.put(f"/api/exams/{i}", json=full(i)).status_code == 204
    return i


def stored(db, a):
    db.expire_all()
    row = db.get(Attempt, a)
    return row, read_attempt(row, {v: k for k, v in subtask_keys(db, row.exam_id).items()})


def test_put_attempt_round_trip_on_time(db, user, exam):
    a = uuid.uuid4()
    grade = {"main": 1.5, "comment": "ok", "marks": {"main": [[{"points": [[0, 0]], "erase": False}]]}, "llm": {"main": {"points": 1}}}
    body = attempt_body(a, exam, grades={"A1a": grade})
    assert user.put(f"/api/attempts/{a}", json=body).status_code == 204
    row, got = stored(db, a)
    assert got == AttemptWire.model_validate(body) and not row.overtime
    assert {x.version for x in db.query(Answer).filter_by(attempt_id=a)} == {"main"}


def test_put_attempt_round_trip_overtime(db, user, exam):
    a = uuid.uuid4()
    body = attempt_body(a, exam, snapshot={"A1a": ans("X")}, answers={"A1a": ans("Y")})
    assert user.put(f"/api/attempts/{a}", json=body).status_code == 204
    row, got = stored(db, a)
    assert row.overtime and got == AttemptWire.model_validate(body)
    rows = {x.version: x.parts[0]["text"] for x in db.query(Answer).filter_by(attempt_id=a)}
    assert rows == {"main": "X", "over": "Y"}


def test_put_attempt_replaces_children(db, user, exam):
    a = uuid.uuid4()
    user.put(f"/api/attempts/{a}", json=attempt_body(a, exam, grades={"A1a": {"main": 1}}))
    assert user.put(f"/api/attempts/{a}", json=attempt_body(a, exam, editedAt=2000)).status_code == 204
    assert db.query(Grade).filter_by(attempt_id=a).count() == 0


def test_put_running_attempt_is_422(user, exam):
    a = uuid.uuid4()
    assert user.put(f"/api/attempts/{a}", json=attempt_body(a, exam, status="running")).status_code == 422


def test_put_attempt_needs_exam(user, exam, monkeypatch):
    other = signed_in(monkeypatch, uuid.uuid4().hex)
    for kw in ({"examId": str(uuid.uuid4())}, {"solutionExamId": str(uuid.uuid4())}):
        a = uuid.uuid4()
        r = user.put(f"/api/attempts/{a}", json=attempt_body(a, exam, **kw))
        assert r.status_code == 409 and r.json()["detail"] == {"code": "need_exam"}
    a = uuid.uuid4()
    assert other.put(f"/api/attempts/{a}", json=attempt_body(a, exam)).status_code == 409


@pytest.mark.parametrize("field,val", [("answers", ans()), ("time", {"main": 1, "over": 0}), ("grades", {"main": 1}), ("snapshot", ans())])
def test_put_attempt_unknown_subtask_is_422(user, exam, field, val):
    a = uuid.uuid4()
    r = user.put(f"/api/attempts/{a}", json=attempt_body(a, exam, **{field: {"Z9z": val}}))
    assert r.status_code == 422


def test_put_attempt_of_other_user_is_404(user, exam, monkeypatch):
    a = uuid.uuid4()
    user.put(f"/api/attempts/{a}", json=attempt_body(a, exam))
    other = signed_in(monkeypatch, uuid.uuid4().hex)
    assert other.put(f"/api/attempts/{a}", json=attempt_body(a, exam, editedAt=9000)).status_code == 404


def test_put_attempt_ignores_stale_edit(db, user, exam):
    a = uuid.uuid4()
    user.put(f"/api/attempts/{a}", json=attempt_body(a, exam, editedAt=2000))
    r = user.put(f"/api/attempts/{a}", json=attempt_body(a, exam, editedAt=1000, fresh=False, answers={}))
    assert r.status_code == 204
    row, got = stored(db, a)
    assert row.fresh and "A1a" in got.answers


def age(db, model, id, **delta):
    db.execute(update(model).where(model.id == id).values(updated_at=func.now() - timedelta(**delta)))
    db.commit()


def test_sync_returns_everything_without_since(db, user):
    e, a = uuid.uuid4(), uuid.uuid4()
    assert user.put(f"/api/exams/{e}", json=full(e, subject="Algebra")).status_code == 204
    body = attempt_body(a, e, grades={"A1a": {"main": 1.5}})
    assert user.put(f"/api/attempts/{a}", json=body).status_code == 204
    out = user.get("/api/sync").json()
    assert [x["id"] for x in out["exams"]] == [str(e)] and out["exams"][0]["subject"] == "Algebra"
    assert "structure" not in out["exams"][0]
    assert out["attempts"] == [AttemptWire.model_validate(body).model_dump(mode="json", by_alias=True)]
    assert out["attempts"][0]["grades"] == {"A1a": {"main": 1.5}}  # unset grade fields are omitted, not null
    assert out["attempts"][0]["snapshot"] is None and out["attempts"][0]["gradedAt"] is None


def test_sync_since_filters_with_overlap(db, user, exam):
    a = uuid.uuid4()
    assert user.put(f"/api/attempts/{a}", json=attempt_body(a, exam)).status_code == 204
    age(db, Exam, exam, hours=1)
    age(db, Attempt, a, seconds=5)
    since = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    out = user.get("/api/sync", params={"since": since}).json()
    assert out["exams"] == [] and [x["id"] for x in out["attempts"]] == [str(a)]
    stamp = db.scalar(select(Attempt.updated_at).where(Attempt.id == a)) + timedelta(seconds=5)
    out = user.get("/api/sync", params={"since": stamp.isoformat()}).json()
    assert [x["id"] for x in out["attempts"]] == [str(a)]


def test_sync_malformed_since_is_422(user):
    assert user.get("/api/sync", params={"since": "yesterday"}).status_code == 422


def test_sync_only_own_records(db, user, exam, monkeypatch):
    a = uuid.uuid4()
    assert user.put(f"/api/attempts/{a}", json=attempt_body(a, exam)).status_code == 204
    other = signed_in(monkeypatch, uuid.uuid4().hex)
    out = other.get("/api/sync").json()
    assert out["exams"] == [] and out["attempts"] == []


def test_sync_cursor_is_db_now(user):
    cursor = datetime.fromisoformat(user.get("/api/sync").json()["cursor"])
    assert abs(datetime.now(UTC) - cursor) < timedelta(seconds=5)


def stale_get(monkeypatch, model, times):
    """The first `times` lookups of `model` miss, as when a concurrent request creates the row between lookup and insert."""
    from sqlalchemy.orm import Session

    real, left = Session.get, [times]

    def get(self, entity, *a, **kw):
        if entity is model and left[0] > 0:
            left[0] -= 1
            return None
        return real(self, entity, *a, **kw)

    monkeypatch.setattr(Session, "get", get)


def test_racing_first_exam_put_updates_instead_of_failing(db, user, monkeypatch):
    i = uuid.uuid4()
    assert user.put(f"/api/exams/{i}", json=full(i)).status_code == 204
    stale_get(monkeypatch, Exam, 1)
    assert user.put(f"/api/exams/{i}", json=full(i, title="Renamed", editedAt=2000)).status_code == 204
    db.expire_all()
    assert db.get(Exam, i).title == "Renamed"


def test_racing_first_attempt_put_updates_instead_of_failing(db, user, exam, monkeypatch):
    i = uuid.uuid4()
    assert user.put(f"/api/attempts/{i}", json=attempt_body(i, exam)).status_code == 204
    stale_get(monkeypatch, Attempt, 2)  # the route's lookup and the writer's
    assert user.put(f"/api/attempts/{i}", json=attempt_body(i, exam, editedAt=2000, extended=True)).status_code == 204
    assert stored(db, i)[0].extended is True


def test_sync_since_the_minimum_datetime_is_a_full_pull(user, exam):
    r = user.get("/api/sync", params={"since": "0001-01-01T00:00:00Z"})
    assert r.status_code == 200
    assert [e["id"] for e in r.json()["exams"]] == [str(exam)]


def pages(user, **first):
    """Follows `more` the way the client does; returns (first page, every attempt id seen in order)."""
    out = user.get("/api/sync", params=first).json()
    first_page, seen = out, [a["id"] for a in out["attempts"]]
    while out["more"]:
        out = user.get("/api/sync", params={"since": out["pageSince"], "after": out["after"]}).json()
        assert out["exams"] == []
        seen += [a["id"] for a in out["attempts"]]
    return first_page, seen


def test_sync_pages_attempts_without_losing_or_repeating_any(db, user, exam, monkeypatch):
    monkeypatch.setattr("app.api.sync.SYNC_PAGE", 2)
    ids = [uuid.uuid4() for _ in range(5)]
    for a in ids:
        assert user.put(f"/api/attempts/{a}", json=attempt_body(a, exam)).status_code == 204
    db.execute(update(Attempt).values(updated_at=func.now()))  # one timestamp for all: only (updated_at, id) tells them apart
    db.commit()
    first, seen = pages(user)
    assert first["more"] and len(first["attempts"]) == 2 and [e["id"] for e in first["exams"]] == [str(exam)]
    assert sorted(seen) == sorted(str(a) for a in ids)


def test_sync_empty_account_is_one_final_page(user):
    out = user.get("/api/sync").json()
    assert (out["more"], out["after"], out["pageSince"], out["attempts"]) == (False, None, None, [])


def test_sync_after_without_since_is_422(user):
    assert user.get("/api/sync", params={"after": str(uuid.uuid4())}).status_code == 422


@pytest.mark.parametrize(
    "field,val",
    [("timeLimitMs", 2**40), ("startedAt", 2**60), ("attendanceAt", 2**40), ("time", {"A1a": {"main": 2**40, "over": 0}}), ("editedAt", -1)],
)
def test_put_attempt_out_of_range_numbers_are_422(user, exam, field, val):
    a = uuid.uuid4()
    assert user.put(f"/api/attempts/{a}", json=attempt_body(a, exam, **{field: val})).status_code == 422


def test_put_exam_duplicate_task_ids_or_huge_times_are_422(user):
    i = uuid.uuid4()
    body = full(i)
    body["structure"]["tasks"] = body["structure"]["tasks"] * 2
    assert user.put(f"/api/exams/{i}", json=body).status_code == 422
    assert user.put(f"/api/exams/{i}", json=full(i, editedAt=2**60)).status_code == 422
