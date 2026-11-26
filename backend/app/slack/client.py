import logging

import httpx

log = logging.getLogger(__name__)


async def revoke(token: str) -> None:
    """Best effort: the row is deleted either way, so a Slack failure is only logged (status, never the token)."""
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.post("https://slack.com/api/auth.revoke", headers={"Authorization": f"Bearer {token}"})
        if r.status_code != 200 or not r.json().get("ok"):
            log.warning("slack revoke failed: %s %s", r.status_code, r.json().get("error") if r.status_code == 200 else "")
    except (httpx.HTTPError, ValueError) as e:
        log.warning("slack revoke failed: %s", type(e).__name__)


async def respond(response_url: str, message: dict, replace_original: bool = True) -> None:
    if not response_url.startswith("https://hooks.slack.com/"):  # the URL comes from the request body: never post to another host
        log.warning("slack respond skipped: unexpected response_url host")
        return
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.post(response_url, json=message | {"replace_original": replace_original})
        if r.status_code != 200:
            log.warning("slack respond failed: %s %s", r.status_code, r.text[:300])
    except httpx.HTTPError as e:
        log.warning("slack respond failed: %s", type(e).__name__)
