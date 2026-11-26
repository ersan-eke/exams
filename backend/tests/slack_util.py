import time

from app.slack.signature import sign


def slack_post(client, path, body: bytes, secret="test", ts=None, content_type="application/json", **headers):
    """POST a body signed the way Slack signs it (the conftest's fake signing secret is "test")."""
    ts = str(int(time.time())) if ts is None else str(ts)
    h = {"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": sign(secret, ts, body), "Content-Type": content_type}
    return client.post(path, content=body, headers=h | headers)
