import uuid

import pytest
from pdf_util import make_pdf
from test_auth import signed_in
from test_documents import upload
from test_sync import full


@pytest.fixture
def user(monkeypatch):
    return signed_in(monkeypatch, uuid.uuid4().hex)


def names(b):
    return [s["name"] for s in b.get("/api/subjects").json()]


def test_create_is_empty_idempotent_and_case_insensitive(user):
    assert names(user) == []
    first = user.post("/api/subjects", json={"name": " GRNVS "}).json()
    assert first["name"] == "GRNVS"
    assert user.post("/api/subjects", json={"name": "grnvs"}).json() == first  # same subject, not a second one
    assert names(user) == ["GRNVS"]
    assert user.post("/api/subjects", json={"name": "  "}).status_code == 422


def test_list_includes_exam_only_deck_only_and_empty_subjects(user):
    i = uuid.uuid4()
    user.put(f"/api/exams/{i}", json=full(i, subject="Exams only"))
    upload(user, make_pdf([["page"]]), subject="Decks only")
    user.post("/api/subjects", json={"name": "Empty"})
    assert names(user) == ["Decks only", "Empty", "Exams only"]


def test_rename_follows_decks_and_exams_and_rejects_duplicates(user):
    i = uuid.uuid4()
    user.put(f"/api/exams/{i}", json=full(i, subject="Old"))
    doc = upload(user, make_pdf([["page"]]), subject="old").json()["document_id"]
    taken = user.post("/api/subjects", json={"name": "Taken"}).json()
    old = user.post("/api/subjects", json={"name": "Old"}).json()
    assert user.patch(f"/api/subjects/{old['id']}", json={"name": "New"}).json() == {"id": old["id"], "name": "New"}
    assert user.get(f"/api/documents/{doc}").json()["subject"] == "New"
    pulled = next(e for e in user.get("/api/sync").json()["exams"] if e["id"] == str(i))
    assert pulled["subject"] == "New" and pulled["editedAt"] > 1000  # newer, so every device takes it
    assert user.patch(f"/api/subjects/{old['id']}", json={"name": "taken"}).json()["detail"] == {"code": "name_taken"}
    assert user.patch(f"/api/subjects/{taken['id']}", json={"name": "TAKEN"}).status_code == 200  # case change of itself


def test_other_users_subjects_are_invisible(user, monkeypatch):
    mine = user.post("/api/subjects", json={"name": "Private"}).json()
    other = signed_in(monkeypatch, uuid.uuid4().hex)
    assert names(other) == []
    assert other.patch(f"/api/subjects/{mine['id']}", json={"name": "Hijack"}).status_code == 404
    assert other.post("/api/subjects", json={"name": "Private"}).json()["id"] != mine["id"]
