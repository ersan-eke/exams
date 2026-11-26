import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app.core import config, crypto
from app.db.models import Integration, User, WebhookEvent


def key():
    return Fernet.generate_key().decode()


def test_round_trip(monkeypatch):
    monkeypatch.setattr(config, "INTEGRATIONS_KEY", key())
    token = crypto.encrypt("xoxb-1")
    assert token != "xoxb-1"
    assert crypto.decrypt(token) == "xoxb-1"


def test_rotation(monkeypatch):
    a, b = key(), key()
    monkeypatch.setattr(config, "INTEGRATIONS_KEY", a)
    old = crypto.encrypt("xoxb-1")
    monkeypatch.setattr(config, "INTEGRATIONS_KEY", f"{b},{a}")
    assert crypto.decrypt(old) == "xoxb-1"
    new = crypto.encrypt("xoxb-2")
    monkeypatch.setattr(config, "INTEGRATIONS_KEY", b)
    assert crypto.decrypt(new) == "xoxb-2"


def test_unset_key_raises(monkeypatch):
    monkeypatch.setattr(config, "INTEGRATIONS_KEY", None)
    with pytest.raises(RuntimeError, match="INTEGRATIONS_KEY not set"):
        crypto.encrypt("x")


def test_integration_unique_per_slack_identity(db):
    users = [User(), User()]
    db.add_all(users)
    db.flush()
    for u in users:
        db.add(
            Integration(user_id=u.id, provider="slack", workspace_id="T1", workspace_name="W", external_user_id="U1", access_token="c", scopes="a")
        )
    with pytest.raises(IntegrityError):
        db.flush()


def test_webhook_event_conflict_is_ignored(db):
    # RETURNING: SQLAlchemy 2.1 reports rowcount -1 for a plain insert, but the real count with RETURNING
    stmt = (
        postgresql.insert(WebhookEvent.__table__)
        .values(provider="slack", event_id="Ev-test-1")
        .on_conflict_do_nothing()
        .returning(WebhookEvent.event_id)
    )
    try:
        assert db.execute(stmt).rowcount == 1
        assert db.execute(stmt).rowcount == 0
    finally:
        db.rollback()


def test_ttl_rejects_old_token(monkeypatch):
    monkeypatch.setattr(config, "INTEGRATIONS_KEY", key())
    token = crypto.encrypt("x")
    assert crypto.decrypt(token, ttl=60) == "x"
    with pytest.raises(InvalidToken):
        crypto.decrypt(token, ttl=-1)
