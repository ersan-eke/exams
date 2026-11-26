"""Sync Notion client for the export job. Errors carry only the status and Notion's `code`, never a token or message."""

import logging
import math
import time
from pathlib import Path

import httpx

from ..core import config

log = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"
MAX_FILE = 5 * 1024 * 1024  # free-workspace limit
MIN_GAP = 0.34  # about 3 requests per second
ATTEMPTS = 5
RETRY = {429, 500, 502, 503, 504}
TITLE = "Flashcards: exam-sim"

_last = 0.0  # shortcut: the gap is per process, not per connection; enough while one worker runs exports


class NotionError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(f"Notion {status} {code}")
        self.status, self.code = status, code


class NotionAuth(NotionError):
    """401: token expired, revoked or the app was removed."""


class NotionGone(NotionError):
    """The database or page is deleted or trashed."""


def _call(method: str, path: str, *, token: str | None = None, auth: tuple[str, str] | None = None, transport=None, **kw) -> dict:
    global _last
    headers = {"Notion-Version": NOTION_VERSION}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with httpx.Client(base_url=NOTION_API, timeout=30, transport=transport, headers=headers, auth=auth) as http:
        for attempt in range(1, ATTEMPTS + 1):
            wait = _last + MIN_GAP - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            r = http.request(method, path, **kw)
            _last = time.monotonic()
            if r.status_code < 400:
                return r.json()
            try:
                err = r.json()
            except ValueError:
                err = {}
            err = err if isinstance(err, dict) else {}
            code = str(err.get("code") or err.get("error") or "")
            if r.status_code in RETRY and attempt < ATTEMPTS:
                try:
                    delay = float(r.headers.get("Retry-After", 1))
                except ValueError:
                    delay = 1
                delay = 1 if math.isnan(delay) else min(max(delay, 0), 30)
                time.sleep(delay)
                continue
            log.warning("notion %s %s -> %s %s", method, path.split("/")[1], r.status_code, code)
            if r.status_code == 401:
                raise NotionAuth(401, code)
            msg = str(err.get("message") or "").lower()
            if (
                r.status_code == 404
                and code == "object_not_found"
                or r.status_code == 400
                and code == "validation_error"
                and ("archived" in msg or "trash" in msg)
            ):
                raise NotionGone(r.status_code, code)
            raise NotionError(r.status_code, code)
    raise AssertionError("unreachable")


def _select(*names: str) -> dict:
    return {"select": {"options": [{"name": n} for n in names]}}


def create_database(token: str, transport: httpx.BaseTransport | None = None) -> tuple[str, str, str]:
    """Workspace-level database plus Board, Gallery and grouped (Subject, Exam, Exam × Task) views; returns (database_id, data_source_id, url)."""
    db = _call(
        "POST",
        "/databases",
        token=token,
        transport=transport,
        json={
            # Notion rejects an omitted parent (400 "body.parent should be defined"), despite its docs
            "parent": {"type": "workspace", "workspace": True},
            "title": [{"type": "text", "text": {"content": TITLE}}],
            "is_inline": False,
            "initial_data_source": {
                "properties": {
                    "Question": {"title": {}},
                    "Subject": _select(),
                    "Exam": _select(),
                    "Task": _select(),
                    "Type": _select("Multiple choice", "Open"),
                    "Score %": {"number": {"format": "percent"}},
                    "Status": _select("New", "Learning", "Known"),
                }
            },
        },
    )
    db_id, ds_id = db["id"], db["data_sources"][0]["id"]
    # the database response lists data sources only, so read the Status property id from the data source
    # views are non-fatal: failing here must not lose the database id, or every retry creates another database
    try:
        props = _call("GET", f"/data_sources/{ds_id}", token=token, transport=transport)["properties"]

        def group(name: str, sort: str = "ascending") -> dict:
            return {"type": "select", "property_id": props[name]["id"], "sort": {"type": sort}}

        base = {"database_id": db_id, "data_source_id": ds_id}
        views = (
            ("Board", {"type": "board", "group_by": group("Status", "manual")}),
            ("Gallery", {"type": "gallery", "cover": {"type": "page_content"}, "cover_size": "large", "cover_aspect": "contain"}),
            ("By subject", {"type": "table", "group_by": group("Subject"), "wrap_cells": False}),
            ("By exam", {"type": "table", "group_by": group("Exam"), "wrap_cells": False}),
            ("Exam × Task", {"type": "board", "group_by": group("Exam"), "sub_group_by": group("Task"), "card_layout": "compact"}),
        )
        for name, conf in views:
            _call("POST", "/views", token=token, transport=transport, json={**base, "name": name, "type": conf["type"], "configuration": conf})
    except (NotionError, KeyError) as e:  # _call already logged a NotionError; a KeyError is a property missing from the response
        if isinstance(e, KeyError):
            log.warning("notion views skipped: data source lacks %s", e)
    return db_id, ds_id, db["url"]


def upload_image(token: str, path: Path, transport: httpx.BaseTransport | None = None) -> str | None:
    """File upload id, or None when the file is missing or too big for the workspace."""
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        return None
    up = _call(
        "POST", "/file_uploads", token=token, transport=transport, json={"mode": "single_part", "filename": path.name, "content_type": "image/png"}
    )
    _call("POST", f"/file_uploads/{up['id']}/send", token=token, transport=transport, files={"file": (path.name, path.read_bytes(), "image/png")})
    return up["id"]


def create_page(token: str, data_source_id: str, properties: dict, children: list[dict], transport: httpx.BaseTransport | None = None) -> str:
    body = {"parent": {"type": "data_source_id", "data_source_id": data_source_id}, "properties": properties, "children": children}
    return _call("POST", "/pages", token=token, transport=transport, json=body)["id"]


def refresh(refresh_token: str, transport: httpx.BaseTransport | None = None) -> dict:
    """Same keys as integrations.exchange_notion; Notion rotates the refresh token, so store both."""
    t = _call(
        "POST",
        "/oauth/token",
        auth=(config.NOTION[0], config.NOTION[1]),
        transport=transport,
        json={"grant_type": "refresh_token", "refresh_token": refresh_token},
    )
    return {
        "access_token": t["access_token"],
        "refresh_token": t.get("refresh_token"),
        "expires_in": t.get("expires_in"),
        "workspace_id": t.get("workspace_id"),
        "workspace_name": t.get("workspace_name"),
        "external_user_id": ((t.get("owner") or {}).get("user") or {}).get("id"),
    }
