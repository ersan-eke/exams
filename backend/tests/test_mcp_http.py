import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_auth import signed_in
from test_db import SAMPLE

from app.db.exams import course_id, to_rows
from app.db.models import AccessToken, Attempt, Grade, Subtask, Task, User
from app.db.session import SessionLocal
from app.mcp import tools
from main import app

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def client(database):
    # one client for the module: the MCP session manager's run() works once per process
    with TestClient(app) as c:
        yield c


def rpc(client, token, method, params=None, **kw):
    headers = HEADERS | ({"Authorization": f"Bearer {token}"} if token else {}) | kw.pop("headers", {})
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return client.post("/mcp", json=body, headers=headers, follow_redirects=False, **kw)


def new_token(monkeypatch, sub):
    browser = signed_in(monkeypatch, sub)
    return browser, browser.post("/api/tokens", json={"name": "cli"}).json()


def tool_names(r):
    return {t["name"] for t in r.json()["result"]["tools"]}


def test_mcp_without_token_is_401(client):
    r = rpc(client, None, "tools/list")
    assert r.status_code == 401 and r.json() == {"detail": "invalid token"}
    assert r.headers["www-authenticate"] == "Bearer"


def test_mcp_bad_token_is_401(client):
    r = rpc(client, "es_nope", "tools/list")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_mcp_lists_tools_at_exact_path(client, monkeypatch):
    _, t = new_token(monkeypatch, uuid.uuid4().hex)
    r = rpc(client, t["token"], "tools/list")
    assert r.status_code == 200
    assert "list_subjects" in tool_names(r)


def test_mcp_accepts_proxied_host(client, monkeypatch):
    _, t = new_token(monkeypatch, uuid.uuid4().hex)
    r = rpc(client, t["token"], "tools/list", headers={"Host": "localhost:5173"})
    assert r.status_code == 200 and "list_subjects" in tool_names(r)


def test_mcp_revoked_token_is_401(client, monkeypatch):
    browser, t = new_token(monkeypatch, uuid.uuid4().hex)
    assert rpc(client, t["token"], "tools/list").status_code == 200
    assert browser.delete(f"/api/tokens/{t['id']}").status_code == 204
    assert rpc(client, t["token"], "tools/list").status_code == 401


def test_token_last_used_is_set(client, monkeypatch):
    browser, t = new_token(monkeypatch, uuid.uuid4().hex)
    rpc(client, t["token"], "tools/list")
    assert browser.get("/api/tokens").json()[0]["lastUsedAt"] is not None


def test_token_last_used_is_written_at_most_hourly(client, monkeypatch):
    _, t = new_token(monkeypatch, uuid.uuid4().hex)

    def last_used(at=None):
        with SessionLocal() as db:
            row = db.get(AccessToken, uuid.UUID(t["id"]))
            if at:
                row.last_used_at = at
                db.commit()
            return row.last_used_at

    recent = last_used(datetime.now(UTC) - timedelta(minutes=30))
    assert rpc(client, t["token"], "tools/list").status_code == 200
    assert last_used() == recent
    stale = last_used(datetime.now(UTC) - timedelta(hours=2))
    assert rpc(client, t["token"], "tools/list").status_code == 200
    assert last_used() > stale + timedelta(hours=1)


def test_mcp_accepts_browser_origin_but_api_writes_stay_same_origin(client, monkeypatch):
    browser, t = new_token(monkeypatch, uuid.uuid4().hex)
    inspector = {"Origin": "http://localhost:6274"}
    assert rpc(client, t["token"], "tools/list", headers=inspector).status_code == 200
    assert browser.post("/api/tokens", json={"name": "x"}, headers=inspector).status_code == 403


def test_list_subjects_counts_and_scores(db):
    user = uuid.uuid4()
    db.add(User(id=user))
    db.flush()
    cid = course_id(db, user, "Analysis")
    exam, solution, hidden = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db.add(to_rows(exam, SAMPLE.model_copy(update={"is_solution": False}), title="E", user_id=user, course_id=cid,
                   point_overrides={"A1b": 2}))  # fmt: skip
    db.add(to_rows(solution, SAMPLE, title="S", user_id=user, course_id=cid))
    db.add(to_rows(hidden, SAMPLE.model_copy(update={"is_solution": False}), title="H", user_id=user, course_id=cid, hidden=True))
    db.flush()
    keys = {k: i for k, i in db.execute(select(Subtask.key, Subtask.id).join(Task).where(Task.exam_id == exam))}
    now = datetime.now(UTC)
    for status in ("handed_in", "running"):
        aid = uuid.uuid4()
        db.add(Attempt(id=aid, user_id=user, exam_id=exam, status=status, fresh=True, started_at=now, time_limit_ms=1,
                       included_task_ids=["A1"], attendance_done=False, mc_rule={"kind": "all_or_nothing"}, extended=False,
                       graded_at=now))  # fmt: skip
        db.flush()
        if status == "handed_in":
            db.add(Grade(attempt_id=aid, subtask_id=keys["A1a"], main=Decimal("0.5")))
            db.add(Grade(attempt_id=aid, subtask_id=keys["A1b"], main=Decimal(2), over=Decimal(1)))
    db.flush()
    assert tools.list_subjects(db, user) == [
        {"subject": "Analysis", "exams": 1, "attempts": 1, "score_share": 1.0}
    ]  # main points, as the app's Results show
    assert tools.list_subjects(db, uuid.uuid4()) == []


def test_mcp_tool_runs_as_token_user(client, monkeypatch):
    _, t = new_token(monkeypatch, uuid.uuid4().hex)
    r = rpc(client, t["token"], "tools/call", {"name": "list_subjects", "arguments": {}})
    assert r.status_code == 200
    assert r.json()["result"]["isError"] is False and r.json()["result"]["structuredContent"] == {"result": []}
