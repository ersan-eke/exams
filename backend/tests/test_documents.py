import uuid

from fastapi.testclient import TestClient
from pdf_util import make_pdf
from sqlalchemy import func, select
from test_auth import signed_in

from app.core.storage import doc_dir
from app.db.models import Chunk, Document, Job
from app.worker.main import run_once
from main import app

CH1 = make_pdf([["Hermite interpolation matches values and derivatives"], ["Newton divided differences table"]])
CH2 = make_pdf([["Gauss quadrature nodes are roots of Legendre polynomials"]])


def upload(browser, pdf, name="ch1.pdf", **form):
    return browser.post("/api/documents", files={"file": (name, pdf, "application/pdf")}, data={"subject": "Numerik", **form})


def test_document_routes_need_sign_in():
    c = TestClient(app)
    assert c.get("/api/documents").status_code == 401
    assert c.post("/api/documents", files={"file": ("a.pdf", CH1, "application/pdf")}).status_code == 401
    assert c.get("/api/subjects").status_code == 401
    assert c.get(f"/api/documents/{uuid.uuid4()}/file").status_code == 401


def test_upload_is_processed_into_page_chunks_and_keeps_the_pdf(db, monkeypatch):
    b = signed_in(monkeypatch, "doc-a")
    r = upload(b, CH1, subject="Numerik", kind="slides")
    assert r.status_code == 202
    doc_id = uuid.UUID(r.json()["document_id"])
    assert db.get(Document, doc_id).page_count == 0  # visible, still waiting for the worker
    assert run_once(db)
    db.expire_all()
    job = db.get(Job, uuid.UUID(r.json()["job_id"]))
    assert job.status == "done" and job.document_id == doc_id
    doc = db.get(Document, doc_id)
    assert doc.page_count == 2 and doc.title == "ch1"
    pages = sorted(db.scalars(select(Chunk.page).where(Chunk.document_id == doc_id)).all())
    assert pages == [1, 2]
    assert b.get(f"/api/documents/{doc_id}/file").content.startswith(b"%PDF-")
    assert [d["title"] for d in b.get("/api/documents", params={"subject": "numerik"}).json()] == ["ch1"]


def test_same_file_twice_returns_the_existing_document(db, monkeypatch):
    b = signed_in(monkeypatch, "doc-b")
    first = upload(b, CH2, "c.pdf").json()
    second = upload(b, CH2, "again.pdf")
    assert second.status_code == 200 and second.json() == {"job_id": None, "document_id": first["document_id"]}


def test_decks_keep_upload_order_and_unfiled_ones_can_be_assigned(db, monkeypatch):
    b = signed_in(monkeypatch, "doc-c")
    a = upload(b, CH1, "one.pdf").json()["document_id"]
    c = upload(b, CH2, "two.pdf", subject="Other").json()["document_id"]
    assert [d["title"] for d in b.get("/api/documents", params={"subject": "Numerik"}).json()] == ["one"]
    assert sorted(d["title"] for d in b.get("/api/documents").json()) == ["one", "two"]  # no subject: all of them
    r = b.patch(f"/api/documents/{c}", json={"subject": "numerik", "title": "Chapter 2", "kind": "script"})
    assert (
        r.json()["subject"] == "Numerik" and r.json()["position"] == 1 and r.json()["kind"] == "script"
    )  # same course, case-insensitive; after "one"
    assert [d["title"] for d in b.get("/api/documents", params={"subject": "Numerik"}).json()] == ["one", "Chapter 2"]
    assert b.patch(f"/api/documents/{a}", json={"subject": None}).json()["subject"] is None  # unfiled
    assert [d["subject"] for d in b.get("/api/documents").json() if d["id"] == a] == [None]
    assert b.patch(f"/api/documents/{a}", json={"subject": "Numerik"}).json()["subject"] == "Numerik"


def test_upload_without_subject_is_rejected(monkeypatch):
    b = signed_in(monkeypatch, "doc-k")
    r = b.post("/api/documents", files={"file": ("a.pdf", CH1, "application/pdf")})
    assert r.status_code == 422 and r.json()["detail"] == {"code": "subject_required"}
    assert b.post("/api/documents", files={"file": ("a.pdf", CH1, "application/pdf")}, data={"subject": "  "}).status_code == 422


def test_foreign_documents_are_404(db, monkeypatch):
    owner = signed_in(monkeypatch, "doc-d")
    doc = upload(owner, CH2, "x.pdf").json()["document_id"]
    run_once(db)
    other = signed_in(monkeypatch, "doc-e")
    assert other.get(f"/api/documents/{doc}/file").status_code == 404
    assert other.patch(f"/api/documents/{doc}", json={"title": "mine"}).status_code == 404
    assert other.delete(f"/api/documents/{doc}").status_code == 404
    assert other.get("/api/documents").json() == []


def test_delete_removes_chunks_and_file(db, monkeypatch):
    b = signed_in(monkeypatch, "doc-f")
    doc = uuid.UUID(upload(b, CH1, "d.pdf").json()["document_id"])
    run_once(db)
    assert (doc_dir(doc) / "file.pdf").exists()
    assert b.delete(f"/api/documents/{doc}").status_code == 204
    assert not doc_dir(doc).exists()
    assert db.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == doc)) == 0


def test_text_free_pdf_fails_and_leaves_no_document(db, monkeypatch):
    b = signed_in(monkeypatch, "doc-g")
    r = upload(b, make_pdf([[]]), "empty.pdf")
    run_once(db)
    db.expire_all()
    assert db.get(Job, uuid.UUID(r.json()["job_id"])).error_code == "scanned"
    assert b.get("/api/documents").json() == []


def test_rejects_non_pdf(monkeypatch):
    b = signed_in(monkeypatch, "doc-h")
    assert upload(b, b"hello", "x.pdf").json()["detail"] == {"code": "not_pdf"}


def test_get_one_document_is_owner_only(db, monkeypatch):
    owner = signed_in(monkeypatch, "doc-i")
    doc = upload(owner, CH2, "one.pdf", subject="Numerik").json()["document_id"]
    assert owner.get(f"/api/documents/{doc}").json()["subject"] == "Numerik"
    assert signed_in(monkeypatch, "doc-j").get(f"/api/documents/{doc}").status_code == 404


def upload_raw(browser, pdf, filename, url="/api/documents", **form):
    """httpx percent-encodes NUL in a multipart filename; a raw client sends it as is."""
    fields = {"subject": "Numerik", **form}
    body = b"".join(f'--X\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items())
    body += f'--X\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: application/pdf\r\n\r\n'.encode()
    return browser.post(url, content=body + pdf + b"\r\n--X--\r\n", headers={"Content-Type": "multipart/form-data; boundary=X"})


def test_upload_cleans_nul_from_title_and_filename(db, monkeypatch):
    b = signed_in(monkeypatch, "doc-nul-a")
    r = upload_raw(b, CH1, "ch\x001.pdf", title="Hermite\x00 notes")
    assert r.status_code == 202
    doc = db.get(Document, uuid.UUID(r.json()["document_id"]))
    assert (doc.title, doc.filename) == ("Hermite notes", "ch1.pdf")
    assert db.get(Job, uuid.UUID(r.json()["job_id"])).filename == "ch1.pdf"


def test_upload_title_falls_back_to_filename_then_upload(db, monkeypatch):
    b = signed_in(monkeypatch, "doc-nul-b")
    r = upload_raw(b, CH1, "ch\x001.pdf", title="\x00 ")
    assert db.get(Document, uuid.UUID(r.json()["document_id"])).title == "ch1"
    r = upload_raw(b, CH2, "\x00.pdf", title="")
    assert db.get(Document, uuid.UUID(r.json()["document_id"])).title == "upload"
    r = upload_raw(b, b"%PDF-1.4 other", "Notes.Pdf", title="")
    assert db.get(Document, uuid.UUID(r.json()["document_id"])).title == "Notes"


def test_exam_upload_cleans_nul_from_filename(db, monkeypatch):
    b = signed_in(monkeypatch, "exam-nul-a")
    r = upload_raw(b, CH1, "mid\x00term.pdf", url="/api/exams")
    assert r.status_code == 202
    assert db.get(Job, uuid.UUID(r.json()["job_id"])).filename == "midterm.pdf"


def test_rename_cleans_nul_and_empty_keeps_the_old_title(db, monkeypatch):
    b = signed_in(monkeypatch, "doc-nul-c")
    doc = upload(b, CH1, "ch1.pdf").json()["document_id"]
    assert b.patch(f"/api/documents/{doc}", json={"title": "Chap\x00ter"}).json()["title"] == "Chapter"
    assert b.patch(f"/api/documents/{doc}", json={"title": "\x00 \x00"}).json()["title"] == "Chapter"


def stored_uploads():
    from app.core.storage import STORAGE_DIR

    return sorted((STORAGE_DIR / "uploads").glob("*.pdf"))


def test_same_file_in_another_subject_is_a_conflict_naming_that_subject(db, monkeypatch):
    b = signed_in(monkeypatch, "doc-dup-a")
    first = upload(b, CH1, subject="Numerik").json()["document_id"]
    before = stored_uploads()
    r = upload(b, CH1, "again.pdf", subject="Algebra")
    assert r.status_code == 409
    assert r.json()["detail"] == {"code": "already_uploaded", "document_id": first, "subject": "Numerik"}
    assert upload(b, CH1, "again.pdf", subject="numerik").status_code == 200  # same Subject, other spelling
    assert [d["subject"] for d in b.get("/api/documents").json()] == ["Numerik"]  # not moved, no empty Subject made
    assert [s["name"] for s in b.get("/api/subjects").json()] == ["Numerik"]
    assert stored_uploads() == before


def test_same_file_unfiled_deck_is_a_conflict_without_subject(db, monkeypatch):
    b = signed_in(monkeypatch, "doc-dup-b")
    first = upload(b, CH2).json()["document_id"]
    assert b.patch(f"/api/documents/{first}", json={"subject": None}).status_code == 200
    r = upload(b, CH2, "again.pdf")
    assert r.status_code == 409 and r.json()["detail"] == {"code": "already_uploaded", "document_id": first, "subject": None}


def test_a_lost_insert_race_answers_like_a_duplicate(db, monkeypatch):
    from app.api import documents

    b = signed_in(monkeypatch, "doc-dup-c")
    first = upload(b, CH1).json()["document_id"]
    before = stored_uploads()
    real, calls = documents._by_sha, []

    def blind_first_time(*a):  # the duplicate check misses; the UNIQUE constraint decides
        calls.append(1)
        return None if len(calls) == 1 else real(*a)

    monkeypatch.setattr(documents, "_by_sha", blind_first_time)
    r = upload(b, CH1, "again.pdf")
    assert r.status_code == 200 and r.json() == {"job_id": None, "document_id": first}
    assert upload(b, CH1, "x.pdf", subject="Algebra").status_code == 409  # the check works again
    monkeypatch.setattr(documents, "_by_sha", blind_first_time)
    calls.clear()
    r = upload(b, CH1, "again.pdf", subject="Algebra")
    assert r.status_code == 409 and r.json()["detail"]["document_id"] == first
    assert stored_uploads() == before
    assert [s["name"] for s in b.get("/api/subjects").json()] == ["Numerik"]  # the loser's new Subject rolled back with its insert


def test_deck_over_the_cap_is_413(db, monkeypatch):
    monkeypatch.setattr("app.api.documents.MAX_BYTES", 1000)
    b = signed_in(monkeypatch, "doc-cap")
    before = db.scalar(select(func.count()).select_from(Job))
    r = upload(b, make_pdf([["x " * 3000]]))
    assert (r.status_code, r.json()["detail"]) == (413, {"code": "too_large"})
    assert db.scalar(select(func.count()).select_from(Job)) == before
