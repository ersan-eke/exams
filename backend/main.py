import logging
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from app.api import ask, auth, chats, documents, integrations, slack, subjects, sync
from app.api.routes import router
from app.core import config
from app.core.config import SECRET_KEY
from app.db.session import SessionLocal
from app.mcp.server import http_app as mcp_app
from app.mcp.server import mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Exam Simulator API", lifespan=lifespan)

# our own INFO lines (e.g. one per grading request) in the uvicorn terminal; not the root logger,
# whose INFO level would also print every outgoing httpx request URL
_app_log = logging.getLogger("app")
_app_log.setLevel(logging.INFO)
if not _app_log.handlers:
    _app_log.addHandler(logging.StreamHandler())

# only holds the OAuth state/PKCE verifier between /login and /callback; the login itself is auth.COOKIE
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="oauth_state", max_age=600)


@app.middleware("http")
async def same_origin_writes(request: Request, call_next):
    """Backs up SameSite=Lax: browsers send Origin on cross-site writes, so refuse ones from other sites."""
    if request.url.path == "/mcp":  # bearer token, never the cookie: nothing for a cross-site page to ride on
        return await call_next(request)
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS") and origin and urlsplit(origin).netloc != request.headers.get("host"):
        return JSONResponse({"detail": "cross-origin request"}, status_code=403)
    return await call_next(request)


def _signed_in(token: str | None) -> bool:
    with SessionLocal() as db:
        return auth.session_user(db, token) is not None


@app.middleware("http")
async def invite_only_uploads(request: Request, call_next):
    """FastAPI reads multipart bodies before dependencies run, so refuse signed-out uploads before up to 100 MB is spooled."""
    upload = request.method == "POST" and request.url.path in ("/api/exams", "/api/documents")
    if config.ALLOWED_EMAILS and upload and not await run_in_threadpool(_signed_in, request.cookies.get(auth.COOKIE)):
        return JSONResponse({"detail": {"code": "sign_in"}}, status_code=401)
    return await call_next(request)


app.include_router(router, prefix="/api")
app.include_router(sync.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(subjects.router, prefix="/api")
app.include_router(ask.router, prefix="/api")
app.include_router(chats.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(integrations.router, prefix="/api")
app.include_router(slack.router, prefix="/api")
# a route, not a mount: a mount answers POST /mcp with a 307 to /mcp/, which MCP clients do not follow
app.add_route("/mcp", mcp_app, methods=["GET", "POST", "DELETE"])


@app.get("/")
def read_root():
    return {"message": "The API is running!"}
