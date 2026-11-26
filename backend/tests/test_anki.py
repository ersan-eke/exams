# ruff: noqa: F811  (the imported seed fixture is used as a test argument)
import json
import re
import sqlite3
import zipfile
from datetime import UTC, datetime
from io import BytesIO

import genanki
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from test_mcp_tools import attempt, committed, seed  # noqa: F401

from app.anki import build_deck
from app.api.auth import current_user
from app.db.exams import course_id
from app.db.models import Course, Subtask, User
from main import app


def deck(db, seed, tmp_path, **kw):
    data = build_deck(db, seed["a"], db.get(Course, course_id(db, seed["a"], "GRNVS")), **kw)
    if data is None:
        return None
    with zipfile.ZipFile(BytesIO(data)) as z:
        z.extract("collection.anki2", tmp_path)
        media = json.loads(z.read("media"))
    notes = sqlite3.connect(tmp_path / "collection.anki2").execute("select guid, flds, tags from notes order by id").fetchall()
    return notes, media


def test_deck_has_one_note_per_weak_subtask(db, seed, tmp_path):
    notes, _ = deck(db, seed, tmp_path)
    assert len(notes) == 2
    source = notes[0][1].split("\x1f")[2]
    assert "Endterm 2024" in source and "0%" in source


def test_nothing_weak_returns_none(db, seed, tmp_path):
    assert deck(db, seed, tmp_path, below=0.0) is None


def test_text_is_html_escaped(db, seed, tmp_path):
    db.execute(update(Subtask).where(Subtask.key == "A1b").values(text="a < b & <script>x</script>"))
    db.flush()
    flds = "".join(n[1] for n in deck(db, seed, tmp_path)[0])
    assert "a &lt; b &amp; &lt;script&gt;" in flds and "<script>" not in flds


def test_subtask_without_solution_still_exports(db, seed, tmp_path):
    db.execute(update(Subtask).where(Subtask.key == "A1a").values(solution_text="", mc_key=[]))
    db.flush()
    notes, _ = deck(db, seed, tmp_path)
    assert "No solution stored" in notes[0][1].split("\x1f")[1]


def test_images_are_embedded_once(db, seed, tmp_path):
    notes, media = deck(db, seed, tmp_path)
    srcs = {s for n in notes for s in re.findall(r'<img src="([^"]+)"', n[1])}
    assert srcs and srcs <= set(media.values())
    assert len(media) == 1  # every crop file in the seed has the same bytes


def test_guids_stable_across_exports(db, seed, tmp_path):
    first = {n[0] for n in deck(db, seed, tmp_path)[0]}
    later = datetime(2026, 11, 2, tzinfo=UTC)
    attempt(db, seed["a"], seed["e1"], {"A1a": 0, "A1b": 1, "A2a": 2, "A2b": 2}, at=later)
    second = {n[0] for n in deck(db, seed, tmp_path)[0]}
    assert first == second and genanki.guid_for(str(seed["e1"]), "A1a") in first


def test_limit(db, seed, tmp_path):
    assert len(deck(db, seed, tmp_path, limit=1)[0]) == 1


@pytest.fixture
def http(committed, db):
    """A client acting as a given seeded user (nobody when called without one)."""

    def as_user(uid=None):
        app.dependency_overrides.clear()
        if uid:
            app.dependency_overrides[current_user] = lambda: db.get(User, uid)
        return TestClient(app)

    yield as_user
    app.dependency_overrides.clear()


def anki(client, db, seed, **params):
    return client.get(f"/api/subjects/{course_id(db, seed['a'], 'GRNVS')}/anki", params=params)


def test_download_is_a_zip_with_the_deck(http, committed, db):
    r = anki(http(committed["a"]), db, committed)
    assert r.status_code == 200 and r.content.startswith(b"PK")
    assert r.headers["content-disposition"] == 'attachment; filename="exam-sim.apkg"'


def test_download_nothing_weak_is_409(http, committed, db):
    r = anki(http(committed["a"]), db, committed, below=0)
    assert r.status_code == 409 and r.json()["detail"] == {"code": "nothing_weak"}


def test_foreign_subject_is_404(http, committed, db):
    assert anki(http(committed["b"]), db, committed).status_code == 404


def test_below_out_of_range_is_422(http, committed, db):
    assert anki(http(committed["a"]), db, committed, below=1.5).status_code == 422


def test_download_needs_login(http, committed, db):
    assert anki(http(), db, committed).status_code == 401


def test_crops_replace_the_extracted_text(db, seed, tmp_path):
    notes, _ = deck(db, seed, tmp_path)
    front = notes[0][1].split("\x1f")[0]
    assert "<img" in front and "<br>" not in front  # the seed has a question crop but no solution crop
