import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_auth import signed_in

from app.api import auth
from app.db.models import AccessToken
from main import app


def test_token_routes_need_sign_in():
    c = TestClient(app)
    assert c.get("/api/tokens").status_code == 401
    assert c.post("/api/tokens", json={"name": "x"}).status_code == 401
    assert c.delete(f"/api/tokens/{uuid.uuid4()}").status_code == 401


def test_create_lists_and_stores_only_hash(db, monkeypatch):
    browser = signed_in(monkeypatch, "tok-a")
    r = browser.post("/api/tokens", json={"name": "laptop"})
    assert r.status_code == 201
    token = r.json()["token"]
    assert token.startswith("es_")
    listed = browser.get("/api/tokens").json()
    assert len(listed) == 1 and listed[0]["name"] == "laptop" and "token" not in listed[0]
    assert listed[0]["lastUsedAt"] is None and isinstance(listed[0]["createdAt"], int)
    row = db.scalar(select(AccessToken).where(AccessToken.id == uuid.UUID(r.json()["id"])))
    assert row.token_hash == auth._hash(token)
    assert token not in (row.name, row.token_hash)


def test_delete_own_token(monkeypatch):
    browser = signed_in(monkeypatch, "tok-b")
    tid = browser.post("/api/tokens", json={"name": "x"}).json()["id"]
    assert browser.delete(f"/api/tokens/{tid}").status_code == 204
    assert browser.get("/api/tokens").json() == []


def test_delete_other_users_token_is_404(db, monkeypatch):
    owner = signed_in(monkeypatch, "tok-c")
    tid = owner.post("/api/tokens", json={"name": "x"}).json()["id"]
    other = signed_in(monkeypatch, "tok-d")
    assert other.delete(f"/api/tokens/{tid}").status_code == 404
    assert db.get(AccessToken, uuid.UUID(tid)) is not None


def test_blank_name_is_422(monkeypatch):
    browser = signed_in(monkeypatch, "tok-e")
    assert browser.post("/api/tokens", json={"name": "  "}).status_code == 422
