import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from slack_util import slack_post
from sqlalchemy import select, update

from app.db.models import Integration, User, WebhookEvent
from app.worker.main import cleanup
from main import app

PATH = "/api/webhooks/slack/events"


def post(body: dict | bytes, **kw):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return slack_post(TestClient(app), PATH, raw, **kw)


def add(db, team) -> uuid.UUID:
    user = User()
    db.add(user)
    db.flush()
    row = Integration(user_id=user.id, provider="slack", workspace_id=team, workspace_name=team, external_user_id="U1", access_token="x", scopes="")
    db.add(row)
    db.commit()
    return row.id


def alive(db, row_id) -> bool:
    db.expire_all()
    return db.get(Integration, row_id) is not None


def event(team, type_="app_uninstalled", event_id=None) -> dict:
    return {"type": "event_callback", "team_id": team, "event_id": event_id or uuid.uuid4().hex, "event": {"type": type_}}


def test_unsigned_bad_and_stale_are_401(db):
    body = b"{}"
    c = TestClient(app)
    assert c.post(PATH, content=body).status_code == 401
    assert post(body, secret="wrong").status_code == 401
    assert post(body, ts=int(time.time()) - 3600).status_code == 401


def test_foreign_origin_is_refused_by_middleware_but_slack_sends_none(db):
    assert post(b"{}", Origin="https://evil.example").status_code == 403  # same_origin_writes
    assert post(b"{}", secret="wrong").status_code == 401  # no Origin, like Slack: reaches the signature check


def test_url_verification_echoes_challenge(db):
    r = post({"type": "url_verification", "challenge": "abc"})
    assert (r.status_code, r.json()) == (200, {"challenge": "abc"})


@pytest.mark.parametrize("type_", ["app_uninstalled", "tokens_revoked"])
def test_uninstall_deletes_that_workspace_only(db, type_):
    team, other = uuid.uuid4().hex, uuid.uuid4().hex
    mine, theirs = add(db, team), add(db, other)
    assert post(event(team, type_)).status_code == 200
    assert not alive(db, mine) and alive(db, theirs)


def test_same_event_id_processes_once(db):
    team, eid = uuid.uuid4().hex, uuid.uuid4().hex
    first = add(db, team)
    assert post(event(team, event_id=eid)).json() == {}
    assert not alive(db, first)
    again = add(db, team)
    assert post(event(team, event_id=eid)).status_code == 200
    assert alive(db, again)


def test_unknown_event_type_changes_nothing(db):
    team = uuid.uuid4().hex
    row = add(db, team)
    assert post(event(team, "message")).status_code == 200
    assert alive(db, row)


@pytest.mark.parametrize("body", [b"not json", b"{}", b"[]"])
def test_malformed_body_is_400(db, body):
    assert post(body).status_code == 400


@pytest.mark.parametrize("event", ["x", [1]])
def test_non_object_event_is_400(db, event):
    body = {"type": "event_callback", "team_id": "T1", "event_id": uuid.uuid4().hex, "event": event}
    assert post(body).status_code == 400


def test_cleanup_drops_events_older_than_a_week(db):
    old, new = uuid.uuid4().hex, uuid.uuid4().hex
    db.add_all([WebhookEvent(provider="slack", event_id=old), WebhookEvent(provider="slack", event_id=new)])
    db.commit()
    db.execute(update(WebhookEvent).where(WebhookEvent.event_id == old).values(received_at=datetime.now(UTC) - timedelta(days=8)))
    db.commit()
    cleanup(db)
    left = set(db.scalars(select(WebhookEvent.event_id)))
    assert new in left and old not in left
