import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from authlib.integrations.starlette_client import OAuthError
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_db import SAMPLE

from app.api import auth
from app.api.auth import allowed, primary_email
from app.core import config
from app.db.exams import to_rows
from app.db.models import Job, LoginSession, User
from main import app


def signed_in(monkeypatch, sub: str, provider: str = "github", email: str | None = None) -> TestClient:
    """A browser (own cookie jar) that went through the callback; the provider round trip is faked."""

    async def fake_identity(p, request):
        return sub, email or f"{sub}@example.com", f"user {sub}"

    monkeypatch.setattr(auth, "identity", fake_identity)
    browser = TestClient(app)
    r = browser.get(f"/api/auth/{provider}/callback", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/")
    return browser


def test_login_redirects_to_provider_with_state_and_pkce():
    r = TestClient(app).get("/api/auth/github/login", follow_redirects=False)
    url = urlsplit(r.headers["location"])
    q = parse_qs(url.query)
    assert f"{url.netloc}{url.path}" == "github.com/login/oauth/authorize"
    assert q["redirect_uri"] == ["http://testserver/api/auth/github/callback"]
    assert q["state"] and q["code_challenge"] and q["code_challenge_method"] == ["S256"]


def test_unknown_provider_is_404():
    assert TestClient(app).get("/api/auth/myspace/login").status_code == 404


def test_callback_creates_user_and_session(db, monkeypatch):
    browser = signed_in(monkeypatch, sub := uuid.uuid4().hex)
    cookie = browser.cookies.get(auth.COOKIE)
    assert cookie
    me = browser.get("/api/me").json()
    assert me["user"]["name"] == f"user {sub}"
    assert set(me["providers"]) == {"github", "google"}
    # only a hash is stored, so a leaked sessions table can't be replayed as cookies
    assert db.get(LoginSession, cookie) is None


def test_same_identity_signs_into_same_user(db, monkeypatch):
    sub = uuid.uuid4().hex
    first = signed_in(monkeypatch, sub).get("/api/me").json()["user"]["id"]
    second = signed_in(monkeypatch, sub).get("/api/me").json()["user"]["id"]
    assert first == second
    assert db.scalar(select(func.count()).select_from(User).where(User.email == f"{sub}@example.com")) == 1


def test_simultaneous_first_logins_share_one_user(db, monkeypatch):
    sub = uuid.uuid4().hex
    first = signed_in(monkeypatch, sub).get("/api/me").json()["user"]["id"]
    real, calls = db.scalar, []

    def stale_lookup(*a, **kw):  # the other request's account row isn't visible yet when this one looks
        calls.append(1)
        return None if len(calls) == 1 else real(*a, **kw)

    monkeypatch.setattr(db, "scalar", stale_lookup)
    token = auth.start_session(db, "github", sub, None, None)
    assert db.get(LoginSession, auth._hash(token)).user_id == uuid.UUID(first)


def test_same_id_at_another_provider_is_another_user(monkeypatch):
    sub = uuid.uuid4().hex
    gh = signed_in(monkeypatch, sub, "github").get("/api/me").json()["user"]["id"]
    google = signed_in(monkeypatch, sub, "google").get("/api/me").json()["user"]["id"]
    assert gh != google


def test_cancelled_consent_goes_back_signed_out(monkeypatch, caplog):
    async def denied(p, request):
        raise OAuthError("access_denied")

    monkeypatch.setattr(auth, "identity", denied)
    browser = TestClient(app)
    r = browser.get("/api/auth/github/callback", follow_redirects=False)
    assert r.headers["location"] == "/?login=failed"
    assert browser.get("/api/me").json()["user"] is None
    assert "github sign-in failed: access_denied" in caplog.text


def test_logout_kills_the_session_server_side(db, monkeypatch):
    browser = signed_in(monkeypatch, uuid.uuid4().hex)
    stolen = browser.cookies.get(auth.COOKIE)
    assert browser.post("/api/auth/logout").status_code == 204
    assert browser.get("/api/me").json()["user"] is None
    replay = TestClient(app, cookies={auth.COOKIE: stolen})
    assert replay.get("/api/me").json()["user"] is None


def test_expired_session_is_ignored(db):
    user = User(id=uuid.uuid4())
    db.add(user)
    db.flush()
    db.add(LoginSession(token_hash=auth._hash("old"), user_id=user.id, expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    assert TestClient(app, cookies={auth.COOKIE: "old"}).get("/api/me").json()["user"] is None


def test_account_exam_only_visible_to_owner(db, monkeypatch):
    owner = signed_in(monkeypatch, uuid.uuid4().hex)
    other = signed_in(monkeypatch, uuid.uuid4().hex)
    exam_id = uuid.uuid4()
    db.add(to_rows(exam_id, SAMPLE, title="mine", user_id=uuid.UUID(owner.get("/api/me").json()["user"]["id"])))
    db.commit()
    assert owner.get(f"/api/exams/{exam_id}").status_code == 200
    assert other.get(f"/api/exams/{exam_id}").status_code == 404
    assert TestClient(app).get(f"/api/exams/{exam_id}").status_code == 404


def test_signed_in_upload_belongs_to_the_user(db, monkeypatch):
    browser = signed_in(monkeypatch, uuid.uuid4().hex)
    r = browser.post("/api/exams", files={"file": ("x.pdf", b"%PDF-1.7 x", "application/pdf")})
    job_id = r.json()["job_id"]
    assert str(db.get(Job, uuid.UUID(job_id)).user_id) == browser.get("/api/me").json()["user"]["id"]
    assert browser.get(f"/api/jobs/{job_id}").status_code == 200
    stranger = TestClient(app)
    assert stranger.get(f"/api/jobs/{job_id}").status_code == 404
    assert stranger.get(f"/api/jobs/{job_id}/events").status_code == 404


def test_upload_keeps_a_cleaned_subject_for_signed_in_exams_only(db, monkeypatch):
    browser = signed_in(monkeypatch, uuid.uuid4().hex)
    pdf = {"file": ("x.pdf", b"%PDF-1.7 x", "application/pdf")}

    def subject_of(client, **data):
        return db.get(Job, uuid.UUID(client.post("/api/exams", files=pdf, data=data).json()["job_id"])).subject

    assert subject_of(browser, subject="a" * 150) == "a" * 100
    assert subject_of(browser, subject="Ana\x00lysis") == "Analysis"
    assert subject_of(browser, subject="a" * 99 + " b") == "a" * 99
    assert subject_of(browser, subject="   ") is None
    assert subject_of(browser, subject="Analysis", role="solution") is None
    assert subject_of(TestClient(app), subject="Analysis") is None


def test_cross_site_writes_are_refused(monkeypatch):
    browser = signed_in(monkeypatch, uuid.uuid4().hex)
    assert browser.post("/api/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert browser.get("/api/me").json()["user"] is not None
    assert browser.post("/api/auth/logout", headers={"Origin": "http://testserver"}).status_code == 204


def test_primary_email_needs_primary_and_verified():
    assert (
        primary_email(
            [
                {"email": "a@x.com", "primary": True, "verified": False},
                {"email": "b@x.com", "primary": False, "verified": True},
            ]
        )
        is None
    )
    assert primary_email([{"email": "c@x.com", "primary": True, "verified": True}]) == "c@x.com"


def test_allowed_is_open_without_list(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_EMAILS", frozenset())
    assert allowed(None) and allowed("anyone@x.com")


def test_allowed_matches_case_insensitively(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_EMAILS", frozenset({"me@x.com"}))
    assert allowed("Me@X.com") and not allowed("other@x.com") and not allowed(None)


def test_callback_denies_unlisted_email(db, monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_EMAILS", frozenset({"me@x.com"}))

    async def fake_identity(p, request):
        return "denied-sub", "stranger@x.com", "s"

    monkeypatch.setattr(auth, "identity", fake_identity)
    browser = TestClient(app)
    r = browser.get("/api/auth/github/callback", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/?login=denied")
    assert not browser.cookies.get(auth.COOKIE)
    assert db.scalar(select(func.count()).select_from(User).where(User.email == "stranger@x.com")) == 0


def test_callback_accepts_listed_email(db, monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_EMAILS", frozenset({"me@x.com"}))
    browser = signed_in(monkeypatch, uuid.uuid4().hex, email="ME@x.com")
    assert browser.cookies.get(auth.COOKIE)


def test_upload_needs_sign_in_when_invite_only(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_EMAILS", frozenset({"me@x.com"}))
    r = TestClient(app).post("/api/exams", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "sign_in"


def test_grade_needs_sign_in_before_key_check(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_EMAILS", frozenset({"me@x.com"}))
    r = TestClient(app).post("/api/grade", json={})  # no X-LLM-Key
    assert r.status_code == 401 and r.json()["detail"]["code"] == "sign_in"


def test_signed_out_upload_still_works_without_list(db, monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_EMAILS", frozenset())
    r = TestClient(app).post("/api/exams", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 202


class FakeClient:
    """Stands in for the Authlib client: GET path -> httpx.Response."""

    def __init__(self, responses):
        self.responses = responses

    async def authorize_access_token(self, request):
        return {"userinfo": self.responses.get("userinfo")}

    async def get(self, path, token=None):
        r = self.responses[path]
        return httpx.Response(r[0], json=r[1], request=httpx.Request("GET", f"https://api.github.com/{path}"))


def fake_provider(monkeypatch, responses):
    monkeypatch.setattr(auth.oauth, "create_client", lambda provider: FakeClient(responses))


def test_github_identity_uses_verified_primary_not_public_email(monkeypatch):
    fake_provider(
        monkeypatch,
        {
            "user": (200, {"id": 7, "login": "oct", "email": "public@x.com"}),
            "user/emails": (200, [{"email": "main@x.com", "primary": True, "verified": True}]),
        },
    )
    assert asyncio.run(auth.identity("github", None)) == ("7", "main@x.com", "oct")


@pytest.mark.parametrize("verified", [False, None])
def test_google_identity_drops_unverified_email(monkeypatch, verified):
    info = {"sub": "g1", "email": "a@x.com", "name": "A"}
    if verified is not None:
        info["email_verified"] = verified
    fake_provider(monkeypatch, {"userinfo": info})
    assert asyncio.run(auth.identity("google", None)) == ("g1", None, "A")


@pytest.mark.parametrize("emails", [(500, {}), (200, {"message": "x"}), (200, [{"primary": True}])])
def test_github_emails_failure_redirects_to_login_failed(db, monkeypatch, emails):
    fake_provider(monkeypatch, {"user": (200, {"id": 7, "login": "oct"}), "user/emails": emails})
    monkeypatch.setattr(config, "ALLOWED_EMAILS", frozenset({"me@x.com"}))
    r = TestClient(app).get("/api/auth/github/callback", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] in ("/?login=failed", "/?login=denied")
    assert (r.headers["location"] == "/?login=failed") == (emails[0] == 500)


def test_signed_in_user_passes_the_gates_when_invite_only(db, monkeypatch):
    browser = signed_in(monkeypatch, uuid.uuid4().hex, email="me@x.com")
    monkeypatch.setattr(config, "ALLOWED_EMAILS", frozenset({"me@x.com"}))
    r = browser.post("/api/exams", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 202
    r = browser.post("/api/grade", json={})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "no_key"


@pytest.mark.parametrize("path", ["/api/exams", "/api/documents"])
def test_signed_out_upload_is_refused_before_the_body_is_read(monkeypatch, path):
    monkeypatch.setattr(config, "ALLOWED_EMAILS", frozenset({"me@x.com"}))

    async def no_form(*a, **k):
        raise AssertionError("multipart body parsed before the sign-in check")

    monkeypatch.setattr("starlette.requests.Request._get_form", no_form)
    r = TestClient(app).post(path, files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")}, data={"subject": "S"})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "sign_in"


def test_signed_in_document_upload_passes_the_gate_when_invite_only(db, monkeypatch):
    browser = signed_in(monkeypatch, uuid.uuid4().hex, email="me@x.com")
    monkeypatch.setattr(config, "ALLOWED_EMAILS", frozenset({"me@x.com"}))
    pdf = b"%PDF-1.4 " + uuid.uuid4().hex.encode()  # unique, so no duplicate answer
    r = browser.post("/api/documents", files={"file": ("a.pdf", pdf, "application/pdf")}, data={"subject": "S"})
    assert r.status_code == 202
