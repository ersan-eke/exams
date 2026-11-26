import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env")  # backend/.env; real env vars win

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://examsim:examsim@localhost:5432/examsim")
# uploaded PDFs (until processed) and rendered crops; shared by the API and the worker
STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", Path(__file__).parents[2] / "storage"))

# signs the short-lived OAuth state cookie; a random fallback only breaks logins in flight during a restart
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_urlsafe(32)
# a provider is offered only when both of its values are set
OAUTH = {name: (os.environ.get(f"{name.upper()}_CLIENT_ID"), os.environ.get(f"{name.upper()}_CLIENT_SECRET")) for name in ("github", "google")}


def parse_allowed_emails(raw: str) -> frozenset[str]:
    emails = frozenset(e.strip().lower() for e in raw.split(",") if e.strip())
    if raw.strip() and not emails:  # "," passes compose's ${ALLOWED_EMAILS:?} but would leave production open
        raise ValueError("ALLOWED_EMAILS is set but holds no email; list at least one or unset it")
    return emails


# invite-only: comma-separated emails allowed to sign in; unset means open (local dev), production compose requires it
ALLOWED_EMAILS = parse_allowed_emails(os.environ.get("ALLOWED_EMAILS", ""))

# dev-only endpoints (the request preview of the AI turn) answer 404 unless DEV=1
DEV = os.environ.get("DEV") == "1"

# Slack (client id, client secret, signing secret) and the Fernet key(s) that encrypt stored integration tokens;
# comma-separated keys allow rotation (newest first). Slack is offered only when all four are set.
SLACK = tuple(os.environ.get(n) or None for n in ("SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET", "SLACK_SIGNING_SECRET"))
INTEGRATIONS_KEY = os.environ.get("INTEGRATIONS_KEY") or None
SLACK_ENABLED = all(SLACK) and bool(INTEGRATIONS_KEY)
NOTION = tuple(os.environ.get(n) or None for n in ("NOTION_CLIENT_ID", "NOTION_CLIENT_SECRET"))
NOTION_ENABLED = all(NOTION) and bool(INTEGRATIONS_KEY)
