import json

import pytest
from conftest import SAMPLES
from fastapi.testclient import TestClient

from app.core.storage import upload_path
from app.worker.main import run_once
from main import app

client = TestClient(app)

CORRUPT = b"%PDF-1.7\n\x00\x01garbage\xff" * 20


def needs(path):
    return pytest.mark.skipif(not path.exists(), reason=f"{path} missing")


def post(path, **data):
    with open(path, "rb") as f:
        return client.post("/api/exams", files={"file": (path.name, f, "application/pdf")}, data=data)


def process(db, r):
    """the whole async flow: queued by the API, one worker pass, then the job and (if done) the exam"""
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    assert r.headers["location"] == f"/api/jobs/{job_id}"
    assert run_once(db)
    job = client.get(f"/api/jobs/{job_id}").json()
    exam = client.get(f"/api/exams/{job['exam_id']}").json() if job["status"] == "done" else None
    return job_id, job, exam


def test_rejects_non_pdf():
    r = client.post("/api/exams", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "not_pdf"


EXAM = SAMPLES / "grnvs" / "grnvs_endterm_2019.pdf"
SOL = SAMPLES / "grnvs" / "grnvs_endterm_2019-solution.pdf"
SCANNED = SAMPLES / "gdb" / "gdb_17_endterm.pdf"


@needs(EXAM)
def test_exam_upload(db):
    _, job, body = process(db, post(EXAM))
    assert job["status"] == "done"
    assert len(body["exam"]["tasks"]) == 6
    for t in body["exam"]["tasks"]:
        for block in t["context"] + t["subtasks"]:
            for reg in block["regions"]:
                assert reg["image"] in body["images"]
    assert body["solution_images"] is None


@needs(SOL)
def test_solution_upload_has_both_variants(db):
    body = process(db, post(SOL))[2]
    assert body["exam"]["is_solution"]
    assert body["images"].keys() == body["solution_images"].keys()
    assert body["images"]["A2b_0.png"] != body["solution_images"]["A2b_0.png"]


@needs(EXAM)
def test_role_solution_adds_solution_images(db):
    body = process(db, post(EXAM, role="solution"))[2]
    assert body["solution_images"] is not None


@needs(SCANNED)
def test_scanned_pdf(db):
    job = process(db, post(SCANNED))[1]
    assert job["status"] == "failed"
    assert job["error_code"] == "scanned"


@needs(EXAM)
def test_uploaded_pdf_removed_after_processing(db):
    job_id = process(db, post(EXAM))[0]
    assert not upload_path(job_id).exists()


@needs(SOL)
def test_solution_upload_has_mc_key(db):
    body = process(db, post(SOL, role="solution"))[2]
    subs = {s["id"]: s for t in body["exam"]["tasks"] for s in t["subtasks"]}
    assert subs["A6e"]["mc_key"] == [0, 2, 3]


def test_corrupt_pdf_is_unreadable(db):
    job_id, job, _ = process(db, client.post("/api/exams", files={"file": ("x.pdf", CORRUPT, "application/pdf")}))
    assert job == {"status": "failed", "stage": "extract", "error_code": "unreadable", "exam_id": None, "document_id": None}
    assert not upload_path(job_id).exists()


def test_events_stream_ends_with_final_state(db):
    job_id = process(db, client.post("/api/exams", files={"file": ("x.pdf", CORRUPT, "application/pdf")}))[0]
    with client.stream("GET", f"/api/jobs/{job_id}/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        data = [json.loads(line[5:]) for line in r.iter_lines() if line.startswith("data:")]
    assert [d["status"] for d in data] == ["failed"]


def test_unknown_job_is_404(db):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/jobs/{missing}").status_code == 404
    assert client.get(f"/api/jobs/{missing}/events").status_code == 404
    assert client.get(f"/api/exams/{missing}").status_code == 404


def test_exam_over_the_cap_is_413_and_exactly_the_cap_passes(db, monkeypatch):
    pdf = CORRUPT
    monkeypatch.setattr("app.api.routes.MAX_EXAM_BYTES", len(pdf) - 1)
    r = client.post("/api/exams", files={"file": ("x.pdf", pdf, "application/pdf")})
    assert (r.status_code, r.json()["detail"]) == (413, {"code": "too_large"})
    monkeypatch.setattr("app.api.routes.MAX_EXAM_BYTES", len(pdf))
    assert client.post("/api/exams", files={"file": ("x.pdf", pdf, "application/pdf")}).status_code == 202


def test_job_stream_gives_up_on_a_stuck_job(db, monkeypatch):
    from app.db.models import Job

    job = Job(filename="x.pdf", role="exam", status="running")
    db.add(job)
    db.commit()
    monkeypatch.setattr("app.api.routes.JOB_EVENTS_DEADLINE", 0.05)
    r = client.get(f"/api/jobs/{job.id}/events")
    events = [json.loads(line[5:]) for line in r.text.splitlines() if line.startswith("data:")]
    assert [e["status"] for e in events] == ["running", "failed"] and events[-1]["error_code"] == "server"


def test_job_stream_keeps_following_a_job_that_beats(monkeypatch):
    import uuid
    from datetime import UTC, datetime

    from app.api.routes import JobOut, _visible_job

    running = JobOut(status="running", stage="export", error_code=None, exam_id=None, document_id=None)
    reads = iter([(running, datetime(2026, 1, 1, 0, 0, i, tzinfo=UTC)) for i in range(2)] + [(running.model_copy(update={"status": "done"}), None)])
    monkeypatch.setattr("app.api.routes._read_job", lambda job_id: next(reads))
    monkeypatch.setattr("app.api.routes.JOB_EVENTS_DEADLINE", 0.5)  # shorter than one poll: only the heartbeat keeps it alive
    app.dependency_overrides[_visible_job] = lambda: uuid.uuid4()
    try:
        r = client.get(f"/api/jobs/{uuid.uuid4()}/events")
    finally:
        app.dependency_overrides.clear()
    events = [json.loads(line[5:]) for line in r.text.splitlines() if line.startswith("data:")]
    assert [e["status"] for e in events] == ["running", "done"]
