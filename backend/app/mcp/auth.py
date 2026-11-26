"""Bearer auth for /mcp: a personal access token resolves to the user id the tools run as."""

import uuid
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from ..api.auth import _hash
from ..db.models import AccessToken
from ..db.session import SessionLocal

current_user_id: ContextVar[uuid.UUID] = ContextVar("current_user_id")


# shortcut: no MCP OAuth 2.1 (needed for one-click claude.ai connectors); add it when publishing as a connector
class BearerAuth:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        scheme, _, token = Headers(scope=scope).get("authorization", "").partition(" ")
        user_id = await run_in_threadpool(_user_for, token) if scheme.lower() == "bearer" and token else None
        if user_id is None:
            response = JSONResponse({"detail": "invalid token"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
            return await response(scope, receive, send)
        current_user_id.set(user_id)
        await self.app(scope, receive, send)


def _user_for(token: str) -> uuid.UUID | None:
    with SessionLocal() as db:
        row = db.scalar(select(AccessToken).where(AccessToken.token_hash == _hash(token)))
        if row is None:
            return None
        now = datetime.now(UTC)
        if row.last_used_at is None or row.last_used_at < now - timedelta(hours=1):  # no write per request
            row.last_used_at = now
            db.commit()
        return row.user_id
