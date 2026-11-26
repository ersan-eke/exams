"""Signed, expiring URLs for page crops: Slack fetches image blocks without credentials."""

import uuid
from pathlib import Path

from cryptography.fernet import InvalidToken

from ..core import crypto
from ..core.storage import CROP_NAME, exam_dir

TTL = 86400


def crop_url(base: str, path: Path) -> str:
    """`path` is <exam_dir>/<layer>/crops/<name>."""
    token = crypto.encrypt(f"{path.parents[2].name}/{path.parents[1].name}/{path.name}")
    return f"{base}/api/slack/crops/{token}"


def crop_file(token: str) -> Path | None:
    try:
        exam, layer, name = crypto.decrypt(token, ttl=TTL).split("/")
        exam_id = uuid.UUID(exam)
    except (InvalidToken, ValueError):
        return None
    if layer not in ("blank", "ink") or not CROP_NAME.fullmatch(name):
        return None
    path = exam_dir(exam_id) / layer / "crops" / name
    if not path.is_file() or not path.resolve().is_relative_to(exam_dir(exam_id).resolve()):
        return None
    return path
