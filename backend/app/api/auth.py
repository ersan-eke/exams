"""Login with GitHub/Google (OAuth 2 authorization code flow + PKCE), then our own server-side session.

The provider only answers "who is this?": its token is dropped right after the callback. Integrations
that act on the user's behalf elsewhere (Notion, Slack) are a different flow that keeps its tokens.
"""

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, StringConstraints
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core import config
from ..core.config import OAUTH
from ..db.models import AccessToken, LoginSession, OAuthAccount, User
from ..db.session import get_db
from ..db.sync import ms

log = logging.getLogger(__name__)
router = APIRouter()

COOKIE = "session"
SESSION_TTL = timedelta(days=30)

PKCE = {"code_challenge_method": "S256"}  # servers without PKCE support ignore it (RFC 7636)
SETTINGS = {
    "github": dict(  # plain OAuth 2, no ID token: identity comes from GET /user, the verified email from GET /user/emails
        authorize_url="https://github.com/login/oauth/authorize",
        access_token_url="https://github.com/login/oauth/access_token",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "user:email", **PKCE},
    ),
    "google": dict(  # OpenID Connect: endpoints and signing keys come from discovery
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile", **PKCE},
    ),
}
PROVIDERS = [name for name, (client_id, secret) in OAUTH.items() if client_id and secret]

oauth = OAuth()
for name in PROVIDERS:
    oauth.register(name, client_id=OAUTH[name][0], client_secret=OAUTH[name][1], **SETTINGS[name])


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def session_user(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    return db.scalar(
        select(User)
        .join(LoginSession, LoginSession.user_id == User.id)
        .where(LoginSession.token_hash == _hash(token), LoginSession.expires_at > func.now())
    )


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Accounts are opt-in, so every route works without one."""
    return session_user(db, request.cookies.get(COOKIE))


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(401)
    return user


def invited_user(user: User | None = Depends(optional_user)) -> User | None:
    """Like optional_user, but with an allowlist set the costly routes need a signed-in user."""
    # shortcut: sessions and MCP tokens of someone removed from the list stay valid until they expire; revoke them on removal once the list changes often
    if config.ALLOWED_EMAILS and user is None:
        raise HTTPException(401, detail={"code": "sign_in"})
    return user


def primary_email(emails: list[dict]) -> str | None:
    if not isinstance(emails, list):
        return None
    return next((e.get("email") for e in emails if isinstance(e, dict) and e.get("primary") and e.get("verified")), None)


def allowed(email: str | None) -> bool:
    return not config.ALLOWED_EMAILS or (email is not None and email.lower() in config.ALLOWED_EMAILS)


def _provider(provider: str) -> str:
    if provider not in PROVIDERS:
        raise HTTPException(404)
    return provider


async def identity(provider: str, request: Request) -> tuple[str, str | None, str | None]:
    """(provider's user id, email, name) of the user coming back from the provider's consent screen."""
    client = oauth.create_client(provider)
    token = await client.authorize_access_token(request)  # checks state, sends the PKCE verifier
    if provider == "google":
        info = token["userinfo"]  # parsed from the ID token after Authlib verified its signature
        return info["sub"], info.get("email") if info.get("email_verified") else None, info.get("name")
    resp = await client.get("user", token=token)
    resp.raise_for_status()
    info = resp.json()
    emails = await client.get("user/emails", token=token)  # a public profile email proves nothing, so only the verified primary counts
    emails.raise_for_status()
    return str(info["id"]), primary_email(emails.json()), info.get("name") or info["login"]


def start_session(db: Session, provider: str, sub: str, email: str | None, name: str | None) -> str:
    """Find or create the user behind this provider identity and open a session; returns the cookie value."""
    by_identity = (OAuthAccount.provider == provider, OAuthAccount.provider_user_id == sub)
    account = db.scalar(select(OAuthAccount).where(*by_identity))
    if account:
        user_id = account.user_id
    else:
        user_id = uuid.uuid4()
        try:
            db.add(User(id=user_id, email=email, name=name))
            db.flush()  # no relationship() between these models, so the user row has to exist before rows pointing at it
            db.add(OAuthAccount(user_id=user_id, provider=provider, provider_user_id=sub))
            db.flush()
        except IntegrityError:  # a simultaneous first login for this identity committed first: join its user
            # shortcut: one re-read of the winner, no retry loop (like sync._once_more_on_conflict); loop if a second conflict is ever seen
            db.rollback()
            user_id = db.scalar(select(OAuthAccount.user_id).where(*by_identity))
            if user_id is None:  # some other constraint failed: not the race
                raise
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=_hash(token), user_id=user_id, expires_at=datetime.now(UTC) + SESSION_TTL))
    db.commit()
    return token


@router.get("/auth/{provider}/login")
async def login(request: Request, provider: str = Depends(_provider)):
    # Vite's proxy keeps the browser's Host header, so this points back at the origin the cookie belongs to
    redirect_uri = str(request.url_for("auth_callback", provider=provider))
    return await oauth.create_client(provider).authorize_redirect(request, redirect_uri)


@router.get("/auth/{provider}/callback", name="auth_callback")
async def callback(request: Request, provider: str = Depends(_provider), db: Session = Depends(get_db)):
    try:
        sub, email, name = await identity(provider, request)
    except OAuthError as e:  # cancelled on the consent screen, or state/PKCE mismatch
        log.warning("%s sign-in failed: %s", provider, e.error)  # an error code only, never a token
        return RedirectResponse("/?login=failed", status_code=303)
    except httpx.HTTPError as e:  # GitHub's user or user/emails call failed
        status = e.response.status_code if isinstance(e, httpx.HTTPStatusError) else type(e).__name__  # never the body or a token
        log.warning("%s sign-in failed: %s", provider, status)
        return RedirectResponse("/?login=failed", status_code=303)
    if not allowed(email):
        log.info("%s sign-in denied", provider)  # never the email
        return RedirectResponse("/?login=denied", status_code=303)
    token = await run_in_threadpool(start_session, db, provider, sub, email, name)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,  # page scripts (and so XSS) can't read it
        samesite="lax",  # not sent on cross-site POSTs: CSRF protection
        secure=request.url.scheme == "https",
    )
    return response


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    if token := request.cookies.get(COOKIE):
        db.execute(delete(LoginSession).where(LoginSession.token_hash == _hash(token)))
        db.commit()
    response.delete_cookie(COOKIE)


@router.get("/me")
def me(user: User | None = Depends(optional_user)):
    return {"user": user and {"id": user.id, "name": user.name, "email": user.email}, "providers": PROVIDERS}


def new_token() -> str:
    return "es_" + secrets.token_urlsafe(32)


class TokenIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


@router.get("/tokens")
def list_tokens(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AccessToken).where(AccessToken.user_id == user.id).order_by(AccessToken.created_at.desc()))
    return [{"id": t.id, "name": t.name, "createdAt": ms(t.created_at), "lastUsedAt": t.last_used_at and ms(t.last_used_at)} for t in rows]


@router.post("/tokens", status_code=201)
def create_token(body: TokenIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    token = new_token()
    row = AccessToken(user_id=user.id, name=body.name, token_hash=_hash(token))
    db.add(row)
    db.commit()
    return {"id": row.id, "name": row.name, "token": token}  # the only time the plaintext exists


@router.delete("/tokens/{token_id}", status_code=204)
def delete_token(token_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(AccessToken).where(AccessToken.id == token_id, AccessToken.user_id == user.id))
    if row is None:
        raise HTTPException(404)
    db.delete(row)
    db.commit()
