"""Connect third-party workspaces (Slack, Notion) to the signed-in user. Unlike login, these tokens are kept (encrypted)."""

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from authlib.integrations.starlette_client import OAuth, OAuthError
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core import config
from ..core.crypto import decrypt, encrypt
from ..db.models import Integration, NotionDatabase, User
from ..db.session import get_db
from ..db.sync import ms
from ..notion.client import NOTION_API, NOTION_VERSION
from ..slack import client
from .auth import current_user, optional_user

log = logging.getLogger(__name__)
router = APIRouter()

oauth = OAuth()
if config.SLACK_ENABLED:
    oauth.register(
        "slack",
        client_id=config.SLACK[0],
        client_secret=config.SLACK[1],
        authorize_url="https://slack.com/oauth/v2/authorize",
        access_token_url="https://slack.com/api/oauth.v2.access",
        client_kwargs={"scope": "commands,chat:write", "code_challenge_method": "S256"},
    )


def _enabled() -> None:
    if not config.SLACK_ENABLED:  # read at call time so tests can flip it
        raise HTTPException(404)


async def exchange(request: Request) -> dict:
    """Finish the OAuth round trip (Authlib checks state and sends the PKCE verifier)."""
    token = await oauth.create_client("slack").authorize_access_token(request)
    return {
        "access_token": token["access_token"],
        "scope": token.get("scope", ""),
        "team_id": token["team"]["id"],
        "team_name": token["team"].get("name") or token["team"]["id"],
        "authed_user_id": token["authed_user"]["id"],
    }


def _notion_enabled() -> None:
    if not config.NOTION_ENABLED:
        raise HTTPException(404)


async def exchange_notion(code: str, redirect_uri: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as http:
        r = await http.post(
            f"{NOTION_API}/oauth/token",
            auth=(config.NOTION[0], config.NOTION[1]),
            headers={"Notion-Version": NOTION_VERSION},
            json={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
        )
        r.raise_for_status()
    t = r.json()
    return {
        "access_token": t["access_token"],
        "refresh_token": t.get("refresh_token"),
        "expires_in": t.get("expires_in"),
        "workspace_id": t["workspace_id"],
        "workspace_name": t.get("workspace_name") or t["workspace_id"],
        "external_user_id": t["owner"]["user"]["id"],
    }


def _save(db: Session, user_id: uuid.UUID, provider: str, t: dict) -> bool:
    """Upsert by (workspace, provider user); False when another account already owns that connection."""
    key = (Integration.provider == provider, Integration.workspace_id == t["workspace_id"], Integration.external_user_id == t["external_user_id"])
    row = db.scalar(select(Integration).where(*key))
    if row and row.user_id != user_id:
        return False
    if row is None:
        row = Integration(user_id=user_id, provider=provider, workspace_id=t["workspace_id"], external_user_id=t["external_user_id"])
        db.add(row)
    row.workspace_name, row.scopes, row.access_token = t["workspace_name"], t.get("scope", ""), encrypt(t["access_token"])
    rt, exp = t.get("refresh_token"), t.get("expires_in")
    row.refresh_token = encrypt(rt) if rt else None
    row.expires_at = datetime.now(UTC) + timedelta(seconds=exp) if exp else None
    if provider == "notion":  # shortcut: one Notion workspace per user; allow several when someone asks for it
        db.flush()
        db.execute(delete(Integration).where(Integration.user_id == user_id, Integration.provider == "notion", Integration.id != row.id))
    try:
        db.commit()
    except IntegrityError:  # a simultaneous connect inserted it first
        db.rollback()
        return False
    return True


@router.get("/integrations")
def list_integrations(user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Integration).where(Integration.user_id == user.id).order_by(Integration.created_at))) if user else []

    def conns(provider: str) -> list[dict]:
        return [{"id": str(r.id), "workspace": r.workspace_name, "connectedAt": ms(r.created_at)} for r in rows if r.provider == provider]

    url = db.scalar(select(NotionDatabase.url).where(NotionDatabase.integration_id.in_([r.id for r in rows if r.provider == "notion"])))
    return {
        "slack": {"enabled": config.SLACK_ENABLED, "connections": conns("slack")},
        "notion": {"enabled": config.NOTION_ENABLED, "connections": conns("notion"), "databaseUrl": url},
    }


@router.get("/integrations/slack/connect", dependencies=[Depends(_enabled), Depends(current_user)])
async def connect(request: Request):
    redirect_uri = str(request.url_for("slack_callback"))
    return await oauth.create_client("slack").authorize_redirect(request, redirect_uri)


@router.get("/integrations/slack/callback", name="slack_callback", dependencies=[Depends(_enabled)])
async def slack_callback(request: Request, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    failed = RedirectResponse("/?integration=failed", status_code=303)
    if user is None:
        return failed
    user_id = user.id  # read before any await/threadpool work touches the session
    try:
        t = await exchange(request)
    except OAuthError as e:  # cancelled on the consent screen, or state/PKCE mismatch
        log.warning("slack connect failed: %s", e.error)  # an error code only, never a token
        return failed
    except (KeyError, TypeError, httpx.HTTPError) as e:  # Slack answered ok=false, without our fields, or not at all
        log.warning("slack connect failed: %s", type(e).__name__)
        return failed
    mapped = {
        "workspace_id": t["team_id"],
        "workspace_name": t["team_name"],
        "external_user_id": t["authed_user_id"],
        "access_token": t["access_token"],
        "scope": t["scope"],
    }
    if not await run_in_threadpool(_save, db, user_id, "slack", mapped):
        log.warning("slack connect failed: connection belongs to another account")
        return failed
    return RedirectResponse("/?integration=slack", status_code=303)


@router.get("/integrations/notion/connect", dependencies=[Depends(_notion_enabled), Depends(current_user)])
def notion_connect(request: Request):
    state = request.session["notion_state"] = secrets.token_urlsafe(32)
    q = {
        "client_id": config.NOTION[0],
        "response_type": "code",
        "owner": "user",
        "redirect_uri": str(request.url_for("notion_callback")),
        "state": state,
    }
    return RedirectResponse(f"{NOTION_API}/oauth/authorize?{urlencode(q)}")


@router.get("/integrations/notion/callback", name="notion_callback", dependencies=[Depends(_notion_enabled)])
async def notion_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    failed = RedirectResponse("/?integration=notion_failed", status_code=303)
    expected = request.session.pop("notion_state", None)
    if user is None or error or not code or not state or not expected or not secrets.compare_digest(state, expected):
        return failed
    user_id = user.id
    try:
        t = await exchange_notion(code, str(request.url_for("notion_callback")))
    except (KeyError, TypeError, ValueError, httpx.HTTPError) as e:  # an error code, a missing field, not JSON, or Notion down
        log.warning("notion connect failed: %s", type(e).__name__)
        return failed
    if not await run_in_threadpool(_save, db, user_id, "notion", t):
        log.warning("notion connect failed: connection belongs to another account")
        return failed
    return RedirectResponse("/?integration=notion", status_code=303)


@router.delete("/integrations/{integration_id}", status_code=204)
async def disconnect(integration_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user_id = user.id

    def load() -> tuple[str | None, bool] | None:
        row = db.scalar(select(Integration).where(Integration.id == integration_id, Integration.user_id == user_id))
        if row is None:
            return None
        others = select(Integration.id).where(
            Integration.provider == row.provider, Integration.workspace_id == row.workspace_id, Integration.id != row.id
        )
        if (
            row.provider != "slack"
        ):  # shortcut: the student also removes a Notion connection in Notion's settings; wire its revoke endpoint when that matters
            return None, False
        try:
            token = decrypt(row.access_token)
        except InvalidToken:  # the key it was sealed with is gone: nothing to revoke, still let the user disconnect
            token = None
        return token, db.scalar(others.limit(1)) is None

    found = await run_in_threadpool(load)
    if found is None:
        raise HTTPException(404)
    token, last = found
    if last and token:  # one bot token per workspace is shared by all its users; revoking it would cut the others off
        await client.revoke(token)

    def remove() -> None:
        db.execute(Integration.__table__.delete().where(Integration.id == integration_id))
        db.commit()

    await run_in_threadpool(remove)
