import base64
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.grading.grader import ADAPTERS, Final, GradingError
from app.grading.limits import RateLimiter, grade_limiter
from main import app

client = TestClient(app)
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nxx").decode()
BODY = {"points": 4, "question": {"text": "Q", "images": []}, "answer": {"text": "A", "images": []}}
OUT = {
    "points": 3,
    "points_min": 2,
    "points_max": 3,
    "feedback": "ok",
    "rubric": [{"item": "a", "max": 4, "hit": 3, "note": "n", "source": "solution"}],
}
KEY = {"X-LLM-Key": "sk-secret"}


@pytest.fixture(autouse=True)
def fake():
    saved = dict(ADAPTERS)
    grade_limiter.hits.clear()

    def install(*events):
        async def adapter(r, key, system, items):
            for e in events:
                if isinstance(e, Exception):
                    raise e
                yield e

        ADAPTERS["anthropic"] = adapter

    install(Final(json.dumps(OUT)))
    yield install
    ADAPTERS.clear()
    ADAPTERS.update(saved)


def events(r):
    return [json.loads(line[5:]) for line in r.text.splitlines() if line.startswith("data:")]


@pytest.mark.parametrize("headers", [{}, {"X-LLM-Key": "  "}])
def test_missing_key_400(headers):
    r = client.post("/api/grade", json=BODY, headers=headers)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "no_key"


def test_too_large_413():
    r = client.post("/api/grade", content=b"{}", headers={**KEY, "Content-Length": "25000001"})
    assert r.status_code == 413


def test_too_large_413_before_key_and_limiter(monkeypatch):
    monkeypatch.setattr("app.api.routes.grade_limiter.allow", lambda _: pytest.fail("used a limiter token"))
    r = client.post("/api/grade", content=b"{}", headers={"Content-Length": "25000001"})
    assert r.status_code == 413


def test_chunked_too_large_413(monkeypatch):
    monkeypatch.setattr("app.api.routes.MAX_GRADE_BYTES", 10)
    r = client.post("/api/grade", content=(b"x" * 8 for _ in range(3)), headers=KEY)
    assert r.status_code == 413


def test_bad_content_length_400():
    r = client.post("/api/grade", content=b"{}", headers={**KEY, "Content-Length": "abc"})
    assert r.status_code == 400


def test_invalid_body_422():
    assert client.post("/api/grade", json={**BODY, "points": 0}, headers=KEY).status_code == 422
    assert client.post("/api/grade", content=b"nope", headers=KEY).status_code == 422


def test_streams_events():
    r = client.post("/api/grade", json=BODY, headers=KEY)
    assert r.headers["content-type"].startswith("text/event-stream")
    assert events(r)[-1]["type"] == "done"


def test_error_event(fake):
    fake(GradingError("bad_key"))
    r = client.post("/api/grade", json=BODY, headers=KEY)
    assert r.status_code == 200
    assert events(r)[-1] == {"type": "error", "code": "bad_key"}
    assert "sk-secret" not in r.text


def test_rate_limit_31st():
    for _ in range(30):
        assert client.post("/api/grade", json=BODY, headers=KEY).status_code == 200
    r = client.post("/api/grade", json=BODY, headers=KEY)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"


def test_limiter_window():
    lim = RateLimiter(limit=2, window=60)
    assert [lim.allow("a", 0), lim.allow("a", 1), lim.allow("a", 2)] == [True, True, False]
    assert lim.allow("b", 2) and lim.allow("a", 61)


def lookups(monkeypatch):
    """Replace the course-material lookup by a recorder; returns the list of its calls."""
    calls = []
    monkeypatch.setattr("app.api.routes.material_for", lambda *a: calls.append(a) or "")
    return calls


@pytest.mark.parametrize("bad", [["not-a-uuid"], [str(uuid.uuid4()) for _ in range(11)]])
def test_exclude_exams_must_be_at_most_ten_uuids(bad, monkeypatch):
    calls = lookups(monkeypatch)
    r = client.post("/api/grade", json=BODY | {"subject": "Numerik", "exclude_exams": bad}, headers=KEY)
    assert r.status_code == 422 and calls == []


def test_exclude_exams_reach_the_material_lookup(monkeypatch):
    calls = lookups(monkeypatch)
    a, b = uuid.uuid4(), uuid.uuid4()
    r = client.post("/api/grade", json=BODY | {"subject": "Numerik", "exclude_exams": [str(a), str(b)]}, headers=KEY)
    assert r.status_code == 200 and events(r)
    assert [(c[1], c[3]) for c in calls] == [("Numerik", [a, b])]


def test_no_subject_means_no_material_lookup(monkeypatch):
    calls = lookups(monkeypatch)
    assert client.post("/api/grade", json=BODY, headers=KEY).status_code == 200
    assert calls == []


def test_limiter_forgets_idle_clients():
    lim = RateLimiter(limit=2, window=60)
    lim.allow("a", 0)
    lim.allow("b", 100)
    assert "a" not in lim.hits and "b" in lim.hits
