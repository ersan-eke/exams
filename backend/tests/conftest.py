import os
import sys
import tempfile
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, delete, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

sys.path.insert(0, str(Path(__file__).parents[1]))

SAMPLES = Path(__file__).parents[2] / "samples"

# before any app import: the app, the worker and alembic all read these at import time
ADMIN_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://examsim:examsim@localhost:5432/examsim")
TEST_URL = make_url(ADMIN_URL).set(database="examsim_test").render_as_string(hide_password=False)
os.environ["DATABASE_URL"] = TEST_URL
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="examsim-storage-")
for _name in ("GITHUB", "GOOGLE"):  # fake credentials so both login providers are registered
    os.environ[f"{_name}_CLIENT_ID"] = os.environ[f"{_name}_CLIENT_SECRET"] = "test"
os.environ.update(SLACK_CLIENT_ID="test", SLACK_CLIENT_SECRET="test", SLACK_SIGNING_SECRET="test")  # SLACK_ENABLED on
os.environ["INTEGRATIONS_KEY"] = Fernet.generate_key().decode()


@pytest.fixture(scope="session")
def database():
    """A fresh database built by replaying every migration, so the migrations themselves are tested."""
    from alembic.config import Config

    from alembic import command

    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            c.execute(text("DROP DATABASE IF EXISTS examsim_test WITH (FORCE)"))
            c.execute(text("CREATE DATABASE examsim_test"))
    except OperationalError:
        pytest.skip("Postgres not reachable, run: docker compose up -d db")
    finally:
        admin.dispose()
    cfg = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_URL)
    command.upgrade(cfg, "head")


@pytest.fixture
def db(database):
    """A session on the test database with an empty job queue, so run_once() takes this test's job."""
    from app.db.models import Job
    from app.db.session import SessionLocal

    with SessionLocal() as s:
        s.execute(delete(Job))
        s.commit()
        yield s
        s.rollback()
        s.execute(delete(Job))
        s.commit()


@pytest.fixture(autouse=True)
def open_sign_in(monkeypatch):
    """A developer's backend/.env allowlist must not change what the tests see."""
    monkeypatch.setattr("app.core.config.ALLOWED_EMAILS", frozenset())


@pytest.fixture(autouse=True)
def enrich_calls(monkeypatch):
    """Docling formulas take seconds per exam and depend on the machine; the worker tests skip them."""
    calls = []
    monkeypatch.setattr("app.worker.main.enrich", lambda *a, **k: calls.append(a))
    return calls


@pytest.fixture(autouse=True)
def fake_embed(monkeypatch):
    """Hashed bag of words: texts that share words get a high cosine, and no model is downloaded."""
    import hashlib
    import math
    import re

    def vec(text):
        v = [0.0] * 384
        for w in re.findall(r"\w+", text.lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 384] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    monkeypatch.setattr("app.rag.embed.embed", lambda texts: [vec(t) for t in texts])
