# ruff: noqa: F811  (the imported seed fixture is used as a test argument)
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_mcp_tools import attempt, seed  # noqa: F401

from app.core.crypto import decrypt, encrypt
from app.db.exams import course_id
from app.db.models import Integration, Job, NotionCard, NotionDatabase
from app.db.session import SessionLocal, engine
from app.notion import export
from app.notion.client import NotionAuth, NotionError, NotionGone


class Fake:
    """In-memory stand-in for the client functions: records calls, hands out ids, raises what a test queues."""

    def __init__(self):
        self.calls, self.fail, self.n = [], {}, 0

    def _next(self, kind):
        self.n += 1
        return f"{kind}{self.n}"

    def _maybe_fail(self, name):
        queue = self.fail.get(name)
        if queue:
            err = queue.pop(0)
            if err:
                raise err

    def create_database(self, token):
        self.calls.append(("create_database", token))
        self._maybe_fail("create_database")
        n = self._next("db")
        return n, "ds-" + n, "https://notion.so/" + n

    def upload_image(self, token, path):
        self._maybe_fail("upload_image")
        self.calls.append(("upload_image", token, path, self._next("up")))
        return self.calls[-1][3]

    def create_page(self, token, data_source_id, properties, children):
        self.calls.append(("create_page", token, data_source_id, properties, children))
        self._maybe_fail("create_page")
        return self._next("page")

    def refresh(self, refresh_token):
        self.calls.append(("refresh", refresh_token))
        self._maybe_fail("refresh")
        n = self._next("")
        return {"access_token": f"access{n}", "refresh_token": f"refresh{n}", "expires_in": 3600, "workspace_id": None, "workspace_name": None}

    def names(self):
        return [c[0] for c in self.calls]

    def pages(self):
        return [c for c in self.calls if c[0] == "create_page"]


@pytest.fixture
def fake(monkeypatch):
    f = Fake()
    for name in ("create_database", "upload_image", "create_page", "refresh"):
        monkeypatch.setattr(export.client, name, getattr(f, name))
    return f


@pytest.fixture
def notion(db, seed):
    """`seed` plus a Notion connection for user a, committed (the exporter commits too)."""
    integ = Integration(
        user_id=seed["a"], provider="notion", workspace_id=uuid.uuid4().hex, workspace_name="W", external_user_id="u",
        access_token=encrypt("access0"), refresh_token=encrypt("refresh0"), scopes="",
    )  # fmt: skip
    db.add(integ)
    db.commit()
    return dict(seed, integ=integ, course=course_id(db, seed["a"], "GRNVS"))


def run(db, s):
    return export.export_subject(db, s["a"], s["course"])


def cards(db, integ):
    return set(db.execute(select(NotionCard.subtask_key).where(NotionCard.integration_id == integ.id)).scalars())


def test_first_export_creates_database_and_one_page_per_weak_subtask(db, notion, fake):
    assert run(db, notion) == 2
    assert fake.names().count("create_database") == 1
    store = db.get(NotionDatabase, notion["integ"].id)
    assert store.database_id == "db1" and store.data_source_id == "ds-db1"
    assert cards(db, notion["integ"]) == {"A1a", "A1b"}
    # each page's body holds exactly the uploads made right before it
    uploaded, per_page = [], []
    for c in fake.calls[1:]:
        if c[0] == "upload_image":
            uploaded.append(c[3])
        elif c[0] == "create_page":
            assert c[2] == "ds-db1"
            per_page.append((uploaded, c[4]))
            uploaded = []
    assert len(per_page) == 2 and any(ids for ids, _ in per_page), "the seed has crops"
    for ids, children in per_page:
        got = [b["image"]["file_upload"]["id"] for b in children if b["type"] == "image"]
        got += [b["image"]["file_upload"]["id"] for b in children[-1]["toggle"]["children"] if b["type"] == "image"]
        assert sorted(got) == sorted(ids)
    assert {c[1] for c in fake.calls} == {"access0"}


def test_second_export_adds_only_new_cards(db, notion, fake):
    run(db, notion)
    attempt(db, notion["a"], notion["e1"], {"A1a": 0, "A1b": 1, "A2a": 0, "A2b": 2}, at=datetime(2026, 11, 2, tzinfo=UTC))
    db.commit()
    before = len(fake.pages())
    assert run(db, notion) == 1
    assert len(fake.pages()) == before + 1 and fake.names().count("create_database") == 1
    assert cards(db, notion["integ"]) == {"A1a", "A1b", "A2a"}


def test_resume_after_crash(db, notion, fake):
    fake.fail["create_page"] = [None, NotionError(500, "internal_server_error")]
    with pytest.raises(NotionError):
        run(db, notion)
    db.rollback()
    assert cards(db, notion["integ"]) == {"A1a"}
    assert run(db, notion) == 1
    assert cards(db, notion["integ"]) == {"A1a", "A1b"}
    assert fake.names().count("create_database") == 1


def test_not_connected(db, seed, fake):
    with pytest.raises(export.ExportFailed) as e:
        export.export_subject(db, seed["a"], course_id(db, seed["a"], "GRNVS"))
    assert e.value.code == "notion_not_connected" and fake.calls == []


def test_nothing_weak_makes_no_notion_call(db, notion, fake, monkeypatch):
    monkeypatch.setattr(export.anki, "BELOW", 0.0)
    with pytest.raises(export.ExportFailed) as e:
        run(db, notion)
    assert e.value.code == "nothing_weak" and fake.calls == []


def test_foreign_course_is_nothing_weak(db, notion, fake):
    other = course_id(db, notion["b"], "Other")
    with pytest.raises(export.ExportFailed) as e:
        export.export_subject(db, notion["a"], other)
    assert e.value.code == "nothing_weak" and fake.calls == []


def test_deleted_database_is_recreated_once(db, notion, fake):
    run(db, notion)
    attempt(db, notion["a"], notion["e1"], {"A1a": 0, "A1b": 1, "A2a": 0, "A2b": 2}, at=datetime(2026, 11, 2, tzinfo=UTC))
    db.commit()
    fake.fail["create_page"] = [NotionGone(404, "object_not_found")]  # the new card finds the database trashed
    assert run(db, notion) == 3  # every weak card is re-sent into the new database
    assert fake.names().count("create_database") == 2
    assert db.get(NotionDatabase, notion["integ"].id).database_id != "db1"
    assert fake.pages()[-1][2] == db.get(NotionDatabase, notion["integ"].id).data_source_id
    assert cards(db, notion["integ"]) == {"A1a", "A1b", "A2a"}


def test_second_gone_ends_the_export(db, notion, fake):
    fake.fail["create_page"] = [NotionGone(404, "object_not_found"), NotionGone(404, "object_not_found")]
    with pytest.raises(export.ExportFailed) as e:
        run(db, notion)
    assert e.value.code == "server" and fake.names().count("create_database") == 2


def test_worker_does_not_retry_a_second_gone(db, notion, fake):
    from app.worker.main import run_once

    job = Job(kind="notion", filename="notion", user_id=notion["a"], course_id=notion["course"])
    db.add(job)
    db.commit()
    fake.fail["create_page"] = [NotionGone(404, "object_not_found")] * 2
    assert run_once(db) and not run_once(db)  # failed, not re-queued
    db.refresh(job)
    assert (job.status, job.error_code, job.attempts) == ("failed", "server", 1)
    assert fake.names().count("create_database") == 2  # the dropped one and its single replacement


def test_each_card_beats_and_the_worker_bumps_locked_at(db, notion, fake, monkeypatch):
    from app.worker.main import run_once

    beats = []
    assert export.export_subject(db, notion["a"], notion["course"], on_card=lambda: beats.append(1)) == 2
    assert len(beats) == 2
    attempt(db, notion["a"], notion["e1"], {"A1a": 0, "A1b": 1, "A2a": 0, "A2b": 2}, at=datetime(2026, 11, 2, tzinfo=UTC))
    job = Job(kind="notion", filename="notion", user_id=notion["a"], course_id=notion["course"])
    db.add(job)
    db.commit()
    claimed = []

    def spy(*a, on_card):
        claimed.append(db.scalar(select(Job.locked_at).where(Job.id == job.id)))
        return export.export_subject(*a, on_card=on_card)

    monkeypatch.setattr("app.worker.main.export_subject", spy)
    assert run_once(db)
    db.refresh(job)
    assert (job.status, job.stage) == ("done", "export") and job.locked_at > claimed[0]


def test_401_refreshes_and_stores_rotated_tokens(db, notion, fake):
    fake.fail["create_database"] = [NotionAuth(401, "unauthorized")]
    assert run(db, notion) == 2
    assert fake.names().count("refresh") == 1 and ("refresh", "refresh0") in fake.calls
    db.refresh(notion["integ"])
    integ = notion["integ"]
    access = decrypt(integ.access_token)
    assert access != "access0" and decrypt(integ.refresh_token) != "refresh0"
    assert integ.workspace_name == "W" and integ.expires_at > datetime.now(UTC)
    assert [c[1] for c in fake.calls if c[0] == "create_page"] == [access, access]


def test_failed_or_missing_refresh_is_notion_auth(db, notion, fake):
    for err in (NotionError(400, "invalid_grant"), NotionAuth(401, "")):
        fake.fail = {"create_database": [NotionAuth(401, "unauthorized")], "refresh": [err]}
        with pytest.raises(export.ExportFailed) as e:
            run(db, notion)
        assert e.value.code == "notion_auth"
    # a second 401 right after a good refresh does not loop
    fake.fail = {"create_database": [NotionAuth(401, ""), NotionAuth(401, "")]}
    with pytest.raises(export.ExportFailed) as e:
        run(db, notion)
    assert e.value.code == "notion_auth" and fake.names().count("refresh") == 3
    notion["integ"].refresh_token = None
    db.commit()
    fake.fail = {"create_database": [NotionAuth(401, "")]}
    with pytest.raises(export.ExportFailed) as e:
        run(db, notion)
    assert e.value.code == "notion_auth" and fake.names().count("refresh") == 3


def test_expiring_token_is_refreshed_first(db, notion, fake):
    notion["integ"].expires_at = datetime.now(UTC) + timedelta(minutes=2)
    db.commit()
    run(db, notion)
    assert fake.names()[0] == "refresh"
    assert {c[1] for c in fake.calls[1:]} == {decrypt(notion["integ"].access_token)}


def test_unuploadable_crop_falls_back_to_text(db, notion, fake, monkeypatch):
    monkeypatch.setattr(export.client, "upload_image", lambda token, path: None)
    assert run(db, notion) == 2
    children = str([p[4] for p in fake.pages()])
    assert "file_upload" not in children and "rich_text" in children


def test_exports_of_one_connection_wait_for_each_other(db, notion, fake):
    done = []

    def other():
        with SessionLocal() as s:
            done.append(export.export_subject(s, notion["a"], notion["course"]))

    with engine.connect() as c:
        c.execute(text("SELECT pg_advisory_lock(:k)"), {"k": export.lock_key(notion["integ"].id)})
        t = threading.Thread(target=other)
        t.start()
        time.sleep(0.5)
        assert fake.calls == [] and not done  # blocked on the lock
        c.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": export.lock_key(notion["integ"].id)})
        t.join(10)
    assert done == [2]
    with engine.connect() as c:  # the export released the lock
        assert c.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": export.lock_key(notion["integ"].id)})
        c.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": export.lock_key(notion["integ"].id)})


# --- POST /api/subjects/{id}/notion ---
from fastapi.testclient import TestClient

from app.api.auth import current_user
from app.db.models import User
from main import app


@pytest.fixture
def http(db):
    def as_user(uid=None):
        app.dependency_overrides.clear()
        if uid:
            app.dependency_overrides[current_user] = lambda: db.get(User, uid)
        return TestClient(app)

    yield as_user
    app.dependency_overrides.clear()


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr("app.core.config.NOTION_ENABLED", True)


def post(client, db, s):
    return client.post(f"/api/subjects/{course_id(db, s['a'], 'GRNVS')}/notion")


def test_post_queues_a_notion_job(db, notion, http, enabled):
    r = post(http(notion["a"]), db, notion)
    assert r.status_code == 202
    job = db.get(Job, uuid.UUID(r.json()["jobId"]))
    assert r.headers["location"] == f"/api/jobs/{job.id}"
    assert (job.kind, job.filename, job.subject, job.course_id, job.user_id, job.status) == (
        "notion", "notion", "GRNVS", notion["course"], notion["a"], "queued",
    )  # fmt: skip


def test_post_twice_returns_the_same_job(db, notion, http, enabled):
    c = http(notion["a"])
    assert post(c, db, notion).json() == post(c, db, notion).json()
    assert len(db.scalars(select(Job).where(Job.kind == "notion")).all()) == 1


def test_post_race_on_the_unique_index_returns_the_winner(db, notion, http, enabled, monkeypatch):
    first = post(http(notion["a"]), db, notion).json()["jobId"]
    real, misses = Session.scalar, [True]

    def scalar(self, q, *a, **k):  # the first active-job lookup misses, as if the other request committed after it
        return None if "jobs.id" in str(q) and misses and misses.pop() else real(self, q, *a, **k)

    monkeypatch.setattr(Session, "scalar", scalar)  # the route's own session, not the test's
    assert post(http(notion["a"]), db, notion).json()["jobId"] == first
    assert misses == [], "the lookup was missed once"


def test_post_race_without_a_winner_reraises(db, notion, http, enabled, monkeypatch):
    post(http(notion["a"]), db, notion)
    real = Session.scalar
    monkeypatch.setattr(Session, "scalar", lambda self, q, *a, **k: None if "jobs.id" in str(q) else real(self, q, *a, **k))  # every lookup misses
    with pytest.raises(IntegrityError):
        post(http(notion["a"]), db, notion)


def test_post_without_connection_is_409(db, seed, http, enabled):
    db.commit()
    r = post(http(seed["a"]), db, seed)
    assert r.status_code == 409 and r.json()["detail"] == {"code": "notion_not_connected"}


def test_post_nothing_weak_is_409(db, notion, http, enabled, monkeypatch):
    monkeypatch.setattr("app.api.subjects.tools.weak_refs", lambda *a: [])
    r = post(http(notion["a"]), db, notion)
    assert r.status_code == 409 and r.json()["detail"] == {"code": "nothing_weak"}


def test_foreign_subject_is_404(db, notion, http, enabled):
    assert post(http(notion["b"]), db, notion).status_code == 404


def test_disabled_is_404(db, notion, http, monkeypatch):
    monkeypatch.setattr("app.core.config.NOTION_ENABLED", False)
    assert post(http(notion["a"]), db, notion).status_code == 404


def test_needs_login(db, notion, http, enabled):
    assert post(http(), db, notion).status_code == 401
