import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_auth import signed_in

from app.api import integrations
from app.core import config
from app.core.crypto import decrypt
from app.db.models import Integration, NotionDatabase
from app.slack import client
from main import app


def fake_exchange(monkeypatch, team="T1", user="U1", token="xoxb-secret"):
    async def ex(request):
        return {"access_token": token, "scope": "commands,chat:write", "team_id": team, "team_name": "Acme", "authed_user_id": user}

    monkeypatch.setattr(integrations, "exchange", ex)


def connect(browser, path="/api/integrations/slack/callback"):
    r = browser.get(path, follow_redirects=False)
    assert r.status_code == 303
    return r.headers["location"]


def rows(db, team):
    db.expire_all()
    return list(db.scalars(select(Integration).where(Integration.workspace_id == team)))


def test_connect_redirects_to_slack_and_needs_session(db, monkeypatch):  # db first: it recreates the test database
    assert TestClient(app).get("/api/integrations/slack/connect").status_code == 401
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    url = urlsplit(b.get("/api/integrations/slack/connect", follow_redirects=False).headers["location"])
    q = parse_qs(url.query)
    assert f"{url.netloc}{url.path}" == "slack.com/oauth/v2/authorize"
    assert q["scope"] == ["commands,chat:write"]
    assert q["state"] and q["code_challenge"] and q["code_challenge_method"] == ["S256"]


def test_callback_stores_encrypted_token_and_list_hides_it(db, monkeypatch):
    team = uuid.uuid4().hex
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    fake_exchange(monkeypatch, team)
    assert connect(b) == "/?integration=slack"
    (row,) = rows(db, team)
    assert row.access_token != "xoxb-secret" and decrypt(row.access_token) == "xoxb-secret"
    body = b.get("/api/integrations").json()
    (c,) = body["slack"]["connections"]
    assert body["slack"]["enabled"] and c["workspace"] == "Acme" and c["id"] == str(row.id)
    assert "token" not in str(body) and "access_token" not in str(body)


def test_reconnect_is_idempotent(db, monkeypatch):
    team = uuid.uuid4().hex
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    fake_exchange(monkeypatch, team, token="old")
    connect(b)
    fake_exchange(monkeypatch, team, token="new")
    assert connect(b) == "/?integration=slack"
    (row,) = rows(db, team)
    assert decrypt(row.access_token) == "new"


def test_other_users_slack_identity_is_refused(db, monkeypatch):
    team = uuid.uuid4().hex
    a = signed_in(monkeypatch, uuid.uuid4().hex)
    fake_exchange(monkeypatch, team, token="first")
    connect(a)
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    fake_exchange(monkeypatch, team, token="second")
    assert connect(b) == "/?integration=failed"
    (row,) = rows(db, team)
    assert decrypt(row.access_token) == "first"


def test_denied_or_signed_out_callback_fails(db, monkeypatch):
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    assert connect(b, "/api/integrations/slack/callback?error=access_denied") == "/?integration=failed"
    fake_exchange(monkeypatch, team := uuid.uuid4().hex)
    assert connect(TestClient(app)) == "/?integration=failed"
    assert rows(db, team) == []


def test_state_mismatch_fails_through_authlib(db, monkeypatch):
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    b.get("/api/integrations/slack/connect", follow_redirects=False)
    assert connect(b, "/api/integrations/slack/callback?code=x&state=forged") == "/?integration=failed"
    assert connect(b, "/api/integrations/slack/callback?code=x") == "/?integration=failed"


def test_delete_revokes_and_removes(db, monkeypatch):
    team = uuid.uuid4().hex
    revoked = []

    async def fake_revoke(token):
        revoked.append(token)

    monkeypatch.setattr(client, "revoke", fake_revoke)
    owner = signed_in(monkeypatch, uuid.uuid4().hex)
    fake_exchange(monkeypatch, team)
    connect(owner)
    (row,) = rows(db, team)
    other = signed_in(monkeypatch, uuid.uuid4().hex)
    assert other.delete(f"/api/integrations/{row.id}").status_code == 404
    assert revoked == [] and len(rows(db, team)) == 1
    assert owner.delete(f"/api/integrations/{row.id}").status_code == 204
    assert revoked == ["xoxb-secret"] and rows(db, team) == []


def test_delete_keeps_shared_token_while_others_use_it(db, monkeypatch):
    team = uuid.uuid4().hex
    revoked = []

    async def fake_revoke(token):
        revoked.append(token)

    monkeypatch.setattr(client, "revoke", fake_revoke)
    a = signed_in(monkeypatch, uuid.uuid4().hex)
    fake_exchange(monkeypatch, team, user="U1")
    connect(a)
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    fake_exchange(monkeypatch, team, user="U2")
    connect(b)
    mine = next(r for r in rows(db, team) if r.external_user_id == "U1")
    assert a.delete(f"/api/integrations/{mine.id}").status_code == 204
    assert revoked == [] and [r.external_user_id for r in rows(db, team)] == ["U2"]


def test_disabled(db, monkeypatch):
    monkeypatch.setattr(config, "SLACK_ENABLED", False)
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    assert b.get("/api/integrations/slack/connect").status_code == 404
    assert b.get("/api/integrations").json()["slack"]["enabled"] is False


def test_slack_outage_in_callback_lands_on_failed(db, monkeypatch):
    async def down(request):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(integrations, "exchange", down)
    assert connect(signed_in(monkeypatch, uuid.uuid4().hex)) == "/?integration=failed"


def test_delete_with_undecryptable_token_still_removes(db, monkeypatch):
    team = uuid.uuid4().hex
    revoked = []

    async def fake_revoke(token):
        revoked.append(token)

    monkeypatch.setattr(client, "revoke", fake_revoke)
    owner = signed_in(monkeypatch, uuid.uuid4().hex)
    fake_exchange(monkeypatch, team)
    connect(owner)
    (row,) = rows(db, team)
    row.access_token = "not-a-fernet-token"
    db.commit()
    assert owner.delete(f"/api/integrations/{row.id}").status_code == 204
    assert revoked == [] and rows(db, team) == []


NOTION_CB = "/api/integrations/notion/callback"


def fake_notion(monkeypatch, ws="W1", user="NU1", access="ntn-access", refresh="ntn-refresh", expires_in=3600):
    async def ex(code, redirect_uri):
        return {
            "access_token": access, "refresh_token": refresh, "expires_in": expires_in,
            "workspace_id": ws, "workspace_name": "Notion Acme", "external_user_id": user,
        }  # fmt: skip

    monkeypatch.setattr(integrations, "exchange_notion", ex)


def notion_on(monkeypatch):
    monkeypatch.setattr(config, "NOTION_ENABLED", True)
    monkeypatch.setattr(config, "NOTION", ("cid", "secret"))


def notion_connect(browser, monkeypatch=None):
    """Run connect (sets the state), then the callback with that state; returns the final location."""
    loc = browser.get("/api/integrations/notion/connect", follow_redirects=False).headers["location"]
    state = parse_qs(urlsplit(loc).query)["state"][0]
    return connect(browser, f"{NOTION_CB}?code=c&state={state}")


def test_notion_connect_sets_state_and_redirects(db, monkeypatch):
    notion_on(monkeypatch)
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    url = urlsplit(b.get("/api/integrations/notion/connect", follow_redirects=False).headers["location"])
    q = parse_qs(url.query)
    assert f"{url.netloc}{url.path}" == "api.notion.com/v1/oauth/authorize"
    assert q["owner"] == ["user"] and q["client_id"] == ["cid"] and q["response_type"] == ["code"]
    assert q["redirect_uri"] == ["http://testserver" + NOTION_CB] and len(q["state"][0]) >= 32
    assert TestClient(app).get("/api/integrations/notion/connect").status_code == 401


def test_notion_callback_saves_encrypted_tokens(db, monkeypatch):
    notion_on(monkeypatch)
    ws = uuid.uuid4().hex
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    fake_notion(monkeypatch, ws)
    assert notion_connect(b) == "/?integration=notion"
    (row,) = rows(db, ws)
    assert row.provider == "notion" and row.access_token != "ntn-access"
    assert decrypt(row.access_token) == "ntn-access" and decrypt(row.refresh_token) == "ntn-refresh"
    assert abs((row.expires_at - datetime.now(UTC)).total_seconds() - 3600) < 60


def test_notion_non_json_token_answer_fails(db, monkeypatch):
    notion_on(monkeypatch)
    b = signed_in(monkeypatch, uuid.uuid4().hex)

    async def ex(code, redirect_uri):
        raise ValueError("Expecting value")  # what r.json() raises on a 200 that is not JSON

    monkeypatch.setattr(integrations, "exchange_notion", ex)
    assert notion_connect(b) == "/?integration=notion_failed"


def test_notion_state_mismatch_fails(db, monkeypatch):
    notion_on(monkeypatch)
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    fake_notion(monkeypatch, ws := uuid.uuid4().hex)
    b.get("/api/integrations/notion/connect", follow_redirects=False)
    assert connect(b, f"{NOTION_CB}?code=c&state=forged") == "/?integration=notion_failed"
    assert connect(b, f"{NOTION_CB}?code=c") == "/?integration=notion_failed"
    assert rows(db, ws) == []


def test_notion_denied_fails(db, monkeypatch):
    notion_on(monkeypatch)
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    b.get("/api/integrations/notion/connect", follow_redirects=False)
    assert connect(b, f"{NOTION_CB}?error=access_denied&state=x") == "/?integration=notion_failed"


def test_notion_reconnect_same_workspace_keeps_row_id(db, monkeypatch):
    notion_on(monkeypatch)
    ws = uuid.uuid4().hex
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    fake_notion(monkeypatch, ws, access="old")
    notion_connect(b)
    (first,) = rows(db, ws)
    fake_notion(monkeypatch, ws, access="new")
    assert notion_connect(b) == "/?integration=notion"
    (row,) = rows(db, ws)
    assert row.id == first.id and decrypt(row.access_token) == "new"


def test_notion_other_workspace_replaces_row(db, monkeypatch):
    notion_on(monkeypatch)
    w1, w2 = uuid.uuid4().hex, uuid.uuid4().hex
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    fake_notion(monkeypatch, w1)
    notion_connect(b)
    fake_notion(monkeypatch, w2)
    assert notion_connect(b) == "/?integration=notion"
    assert rows(db, w1) == [] and len(rows(db, w2)) == 1


def test_notion_identity_of_another_user_is_refused(db, monkeypatch):
    notion_on(monkeypatch)
    ws = uuid.uuid4().hex
    a = signed_in(monkeypatch, uuid.uuid4().hex)
    fake_notion(monkeypatch, ws, access="first")
    notion_connect(a)
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    fake_notion(monkeypatch, ws, access="second")
    assert notion_connect(b) == "/?integration=notion_failed"
    (row,) = rows(db, ws)
    assert decrypt(row.access_token) == "first"


def test_notion_disabled_is_404(db, monkeypatch):
    monkeypatch.setattr(config, "NOTION_ENABLED", False)
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    assert b.get("/api/integrations/notion/connect").status_code == 404
    assert b.get(NOTION_CB).status_code == 404
    assert b.get("/api/integrations").json()["notion"]["enabled"] is False


def test_list_separates_slack_and_notion(db, monkeypatch):
    notion_on(monkeypatch)
    sw, nw = uuid.uuid4().hex, uuid.uuid4().hex
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    fake_exchange(monkeypatch, sw)
    connect(b)
    fake_notion(monkeypatch, nw)
    notion_connect(b)
    body = b.get("/api/integrations").json()
    assert [c["workspace"] for c in body["slack"]["connections"]] == ["Acme"]
    assert [c["workspace"] for c in body["notion"]["connections"]] == ["Notion Acme"] and body["notion"]["databaseUrl"] is None
    (nrow,) = rows(db, nw)
    db.add(NotionDatabase(integration_id=nrow.id, database_id="d", data_source_id="s", url="https://notion.so/d"))
    db.commit()
    assert b.get("/api/integrations").json()["notion"]["databaseUrl"] == "https://notion.so/d"
    assert "ntn-" not in str(body)


def test_disconnect_notion_does_not_call_slack_revoke(db, monkeypatch):
    notion_on(monkeypatch)
    revoked = []

    async def fake_revoke(token):
        revoked.append(token)

    monkeypatch.setattr(client, "revoke", fake_revoke)
    ws = uuid.uuid4().hex
    b = signed_in(monkeypatch, uuid.uuid4().hex)
    fake_notion(monkeypatch, ws)
    notion_connect(b)
    (row,) = rows(db, ws)
    assert b.delete(f"/api/integrations/{row.id}").status_code == 204
    assert revoked == [] and rows(db, ws) == []
