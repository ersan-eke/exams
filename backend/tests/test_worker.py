import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text, update
from test_auth import signed_in
from test_db import SAMPLE
from test_documents import CH1, upload

from app.core.storage import doc_dir, exam_dir
from app.db.exams import to_rows
from app.db.models import Course, Document, Exam, Job, User
from app.db.session import SessionLocal
from app.notion.export import ExportFailed
from app.rag.index import backfill_decks, store_deck
from app.worker.main import MAX_ATTEMPTS, claim, cleanup, guarded_step, run_once


def add_job(db, **cols) -> uuid.UUID:
    job = Job(**{"filename": "x.pdf", "role": "exam"} | cols)
    db.add(job)
    db.commit()
    return job.id


def test_locked_job_is_skipped_not_waited_for(db):
    add_job(db)
    with SessionLocal() as other:
        other.scalars(select(Job).with_for_update()).one()  # another worker is mid-claim
        db.execute(text("SET lock_timeout = '2s'"))  # without SKIP LOCKED this would block, then fail
        assert claim(db) is None
        other.rollback()
    assert claim(db) is not None


def test_stale_job_is_reclaimed_then_given_up(db):
    old = datetime.now(UTC) - timedelta(hours=1)
    job_id = add_job(db, status="running", locked_at=old, attempts=3)  # its worker died three times
    assert run_once(db)
    job = db.get(Job, job_id)
    assert (job.status, job.error_code) == ("failed", "server")


def test_crash_requeues_the_job(db, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db hiccup")

    monkeypatch.setattr("app.worker.main.process", boom)
    job_id = add_job(db)
    assert run_once(db)
    job = db.get(Job, job_id)
    assert (job.status, job.attempts, job.finished_at) == ("queued", 1, None)


def test_cleanup_drops_old_anonymous_exams(db):
    old, new = uuid.uuid4(), uuid.uuid4()
    db.add_all([to_rows(old, SAMPLE, title="old"), to_rows(new, SAMPLE, title="new")])
    db.commit()
    db.execute(update(Exam).where(Exam.id == old).values(created_at=datetime.now(UTC) - timedelta(days=2)))
    db.commit()
    exam_dir(old).mkdir(parents=True)
    cleanup(db)
    assert db.get(Exam, old) is None and not exam_dir(old).exists()
    assert db.get(Exam, new) is not None


def fake_pipeline(monkeypatch):
    """process() with the PDF stages replaced: only the filing under a course is under test"""
    monkeypatch.setattr("app.worker.main.extract", lambda pdf: [])
    monkeypatch.setattr("app.worker.main.group", lambda *a, **k: SAMPLE)
    monkeypatch.setattr("app.worker.main.render_variants", lambda *a, **k: {"ink": None})


def exam_of(db, job_id) -> Exam:
    db.expire_all()
    return db.get(Exam, db.get(Job, job_id).exam_id)


def test_worker_enriches_between_extract_and_group(db, monkeypatch, enrich_calls):
    fake_pipeline(monkeypatch)
    add_job(db)
    assert run_once(db)
    assert len(enrich_calls) == 1 and enrich_calls[0][1] == []  # (pdf, pages)


def test_retry_after_a_crash_skips_enrichment(db, monkeypatch, enrich_calls):
    fake_pipeline(monkeypatch)
    old = datetime.now(UTC) - timedelta(hours=1)
    job_id = add_job(db, status="running", locked_at=old, attempts=1)  # its worker died once
    assert run_once(db)
    assert db.get(Job, job_id).attempts == 2 and enrich_calls == []


def test_signed_in_jobs_with_the_same_subject_share_one_course(db, monkeypatch):
    fake_pipeline(monkeypatch)
    user = User(email=f"{uuid.uuid4().hex}@example.com")
    db.add(user)
    db.commit()
    ids = [add_job(db, user_id=user.id, subject="Analysis") for _ in range(2)]
    assert run_once(db) and run_once(db)
    exams = [exam_of(db, i) for i in ids]
    assert exams[0].course_id is not None and exams[0].course_id == exams[1].course_id
    assert db.scalar(select(func.count()).select_from(Course).where(Course.user_id == user.id)) == 1


def test_no_course_without_a_user_or_a_subject(db, monkeypatch):
    fake_pipeline(monkeypatch)
    user = User(email=f"{uuid.uuid4().hex}@example.com")
    db.add(user)
    db.commit()
    anonymous = add_job(db, subject="Analysis")
    no_subject = add_job(db, user_id=user.id)
    assert run_once(db) and run_once(db)
    assert exam_of(db, anonymous).course_id is None
    assert exam_of(db, no_subject).course_id is None


def test_exam_title_is_cleaned_and_capped(db, monkeypatch):
    fake_pipeline(monkeypatch)
    job_id = add_job(db, filename="a" * 300 + ".pdf")
    assert run_once(db)
    assert exam_of(db, job_id).title == "a" * 200


def test_exam_title_falls_back_when_the_filename_cleans_to_nothing(db, monkeypatch):
    fake_pipeline(monkeypatch)
    job_id = add_job(db, filename="  .pdf")  # the route already strips NUL; the worker must cope with what is left
    assert run_once(db)
    assert exam_of(db, job_id).title == "upload"


def queue_deck(db, monkeypatch, name):
    r = upload(signed_in(monkeypatch, name), CH1)
    return uuid.UUID(r.json()["job_id"]), uuid.UUID(r.json()["document_id"])


def test_deck_deleted_while_queued_finishes_the_job(db, monkeypatch):
    job_id, doc_id = queue_deck(db, monkeypatch, "w-queued")
    db.execute(text("delete from documents where id = :i"), {"i": doc_id})
    db.commit()
    assert run_once(db)
    db.expire_all()
    assert db.get(Job, job_id).status == "done"


def test_deck_deleted_mid_job_does_not_kill_the_worker(db, monkeypatch):
    job_id, doc_id = queue_deck(db, monkeypatch, "w-mid")
    real = store_deck

    def delete_meanwhile(db_, doc, pages):
        real(db_, doc, pages)
        with SessionLocal() as other:
            other.execute(text("delete from documents where id = :i"), {"i": doc_id})
            other.commit()

    monkeypatch.setattr("app.worker.main.store_deck", delete_meanwhile)
    assert run_once(db)
    db.expire_all()
    assert db.get(Job, job_id).status in ("queued", "done")
    assert run_once(db)  # the retry finds no Deck and is done
    db.expire_all()
    assert db.get(Job, job_id).status == "done" and db.get(Document, doc_id) is None


def test_server_failure_keeps_the_deck_and_the_idle_worker_finishes_it(db, monkeypatch):
    job_id, doc_id = queue_deck(db, monkeypatch, "w-server")
    db.execute(update(Job).where(Job.id == job_id).values(attempts=MAX_ATTEMPTS + 1))
    db.commit()
    assert run_once(db)
    db.expire_all()
    job = db.get(Job, job_id)
    assert (job.status, job.error_code) == ("failed", "server")
    assert db.get(Document, doc_id) is not None and (doc_dir(doc_id) / "file.pdf").read_bytes() == CH1
    while backfill_decks(db):  # the kept PDF lets the idle worker read it later (other tests' file-less Decks are skipped on the way)
        pass
    db.expire_all()
    assert db.get(Document, doc_id).page_count == 2


def test_unreadable_pdf_still_removes_the_deck(db, monkeypatch):
    job_id, doc_id = queue_deck(db, monkeypatch, "w-unread")

    def boom(_):
        raise ValueError

    monkeypatch.setattr("app.worker.main.read_deck", boom)
    assert run_once(db)
    db.expire_all()
    assert db.get(Job, job_id).error_code == "unreadable" and db.get(Document, doc_id) is None


def test_a_failing_loop_step_is_survived(db, monkeypatch):
    def boom(_):
        raise RuntimeError("db restarting")

    monkeypatch.setattr("app.worker.main.step", boom)
    guarded_step()  # must not raise


@pytest.fixture
def signed_in_user(db):
    user = User(email=f"{uuid.uuid4().hex}@example.com")
    db.add(user)
    db.commit()
    return user.id


def test_worker_runs_a_notion_job_to_done(db, monkeypatch, signed_in_user):
    calls = []
    monkeypatch.setattr("app.worker.main.export_subject", lambda *a, **k: calls.append(a) or 1)
    job_id = add_job(db, kind="notion", filename="notion", user_id=signed_in_user)
    assert run_once(db)
    job = db.get(Job, job_id)
    assert (job.status, job.error_code, len(calls)) == ("done", None, 1)


def test_worker_maps_export_failed_to_error_code(db, monkeypatch, signed_in_user):
    def fail(*a, **k):
        raise ExportFailed("notion_auth")

    monkeypatch.setattr("app.worker.main.export_subject", fail)
    job_id = add_job(db, kind="notion", filename="notion", user_id=signed_in_user)
    assert run_once(db)
    job = db.get(Job, job_id)
    assert (job.status, job.error_code, job.attempts) == ("failed", "notion_auth", 1)


def test_worker_retries_other_errors_then_gives_up(db, monkeypatch, signed_in_user):
    def boom(*a, **k):
        raise RuntimeError("notion down")

    monkeypatch.setattr("app.worker.main.export_subject", boom)
    job_id = add_job(db, kind="notion", filename="notion", user_id=signed_in_user)
    for _ in range(MAX_ATTEMPTS):
        assert run_once(db)
    job = db.get(Job, job_id)
    assert (job.status, job.error_code, job.attempts) == ("failed", "server", MAX_ATTEMPTS)
