import hmac
import time
from hashlib import sha256

from fastapi import HTTPException, Request

from app.core import config

MAX_SKEW = 300


def sign(secret: str, timestamp: str, body: bytes) -> str:
    base = b"v0:" + timestamp.encode() + b":" + body
    return "v0=" + hmac.new(secret.encode(), base, sha256).hexdigest()


def verify(secret: str, timestamp: str | None, signature: str | None, body: bytes, now: float | None = None) -> bool:
    try:
        ts = int(timestamp or "")
        skew = abs((time.time() if now is None else now) - ts)  # int("9"*400) parses, but float() overflows
    except (ValueError, OverflowError):
        return False
    if skew > MAX_SKEW or not signature:
        return False
    return hmac.compare_digest(sign(secret, str(ts), body).encode(), signature.encode())


async def verified_body(request: Request) -> bytes:
    if not config.SLACK_ENABLED:
        raise HTTPException(404)
    body = await request.body()
    h = request.headers
    if not verify(config.SLACK[2], h.get("x-slack-request-timestamp"), h.get("x-slack-signature"), body):
        raise HTTPException(401, "bad Slack signature")
    return body
