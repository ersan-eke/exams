"""Slack webhooks. Every webhook route checks Slack's signature first (`verified_body`), so no session or CORS applies.
The one exception is GET /slack/crops/{token}: Slack fetches images without credentials, so the signed expiring token is the credential."""

import json
from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..core import config
from ..db.models import Integration, WebhookEvent
from ..db.session import get_db
from ..slack import blocks, client, crops, quiz
from ..slack.signature import verified_body

router = APIRouter()


def _handle(db: Session, team_id: str, event_id: str, kind: str) -> None:
    # rowcount is -1 for ON CONFLICT DO NOTHING here, so RETURNING tells a first delivery from a retry
    new = db.scalar(insert(WebhookEvent).values(provider="slack", event_id=event_id).on_conflict_do_nothing().returning(WebhookEvent.event_id))
    if new is not None and kind in ("app_uninstalled", "tokens_revoked"):
        db.execute(delete(Integration).where(Integration.provider == "slack", Integration.workspace_id == team_id))
    db.commit()


@router.post("/webhooks/slack/events")
async def events(body: bytes = Depends(verified_body), db: Session = Depends(get_db)):
    try:
        data = json.loads(body)
        kind = data["type"]
    except (ValueError, KeyError, TypeError):  # TypeError: a JSON list or scalar
        raise HTTPException(400, "bad body") from None
    if kind == "url_verification":
        return {"challenge": data.get("challenge", "")}
    if kind == "event_callback":
        ev = data.get("event", {})
        if not isinstance(ev, dict):
            raise HTTPException(400, "bad body")
        # shortcut: handled inline; move to the job queue when a handler does slow work (5d)
        await run_in_threadpool(_handle, db, str(data.get("team_id", "")), str(data.get("event_id", "")), str(ev.get("type", "")))
    return {}


@router.get("/slack/crops/{token}")
async def crop(token: str):
    path = crops.crop_file(token) if config.SLACK_ENABLED else None
    if path is None:
        raise HTTPException(404)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


def _form(body: bytes) -> dict[str, str]:
    try:
        return {k: v[0] for k, v in parse_qs(body.decode(), strict_parsing=True, keep_blank_values=True).items()}
    except ValueError:
        raise HTTPException(400, "bad body") from None


def _command(db: Session, team: str, user: str, text: str, base: str) -> dict:
    uid = quiz.linked_user(db, team, user)
    return blocks.connect_message(f"{base}/") if uid is None else quiz.question(db, uid, text, base)


@router.post("/webhooks/slack/commands")
async def commands(request: Request, tasks: BackgroundTasks, body: bytes = Depends(verified_body), db: Session = Depends(get_db)):
    f = _form(body)
    if "team_id" not in f or "user_id" not in f:
        raise HTTPException(400, "bad body")
    base = str(request.base_url).rstrip("/")
    message = await run_in_threadpool(_command, db, f["team_id"], f["user_id"], f.get("text", ""), base)
    if not f.get("response_url"):
        return message
    # Slack validates an inline reply (and fetches its images) inside 3 s; acknowledge at once and post via response_url
    tasks.add_task(client.respond, f["response_url"], message, False)
    return Response()


def _interact(db: Session, team: str, user: str, ref: str, choice: int | None, base: str) -> dict:
    uid = quiz.linked_user(db, team, user)
    return blocks.connect_message(f"{base}/") if uid is None else quiz.answer(db, uid, ref, choice, base)


@router.post("/webhooks/slack/interactions")
async def interactions(request: Request, tasks: BackgroundTasks, body: bytes = Depends(verified_body), db: Session = Depends(get_db)):
    try:
        data = json.loads(_form(body)["payload"])
        action = data["actions"][0]
        team, user, url = data["team"]["id"], data["user"]["id"], data["response_url"]
        kind, value = action["action_id"], action["value"]
        if not isinstance(value, str):
            raise TypeError
        if kind == "answer":
            ref, _, idx = value.rpartition("|")
            choice = int(idx)
            if not ref:
                raise ValueError
        elif kind == "reveal":
            ref, choice = value, None
        else:
            raise ValueError
        if not all(isinstance(x, str) for x in (team, user, url, ref)):
            raise ValueError
    except (ValueError, KeyError, IndexError, TypeError):  # TypeError: a non-dict shape
        raise HTTPException(400, "bad body") from None
    base = str(request.base_url).rstrip("/")
    message = await run_in_threadpool(_interact, db, team, user, ref, choice, base)
    tasks.add_task(client.respond, url, message)
    return {}
