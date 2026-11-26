import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.db.models import Course, Exam, Integration, Job, NotionCard, NotionDatabase, User


def setup_rows(db):
    user = User(email=f"{uuid.uuid4().hex}@example.com")
    db.add(user)
    db.flush()
    course = Course(user_id=user.id, name=uuid.uuid4().hex)
    exams = [
        Exam(id=uuid.uuid4(), user_id=user.id, title="E", source="e.pdf", page_count=1, page_sizes=[], kind="digital", is_solution=False)
        for _ in range(2)
    ]
    integ = Integration(
        user_id=user.id, provider="notion", workspace_id=uuid.uuid4().hex, workspace_name="W", external_user_id="u", access_token="x", scopes=""
    )
    db.add_all([course, *exams, integ])
    db.flush()
    db.add(NotionDatabase(integration_id=integ.id, database_id="d", data_source_id="ds", url="https://notion.so/d"))
    db.add_all([NotionCard(integration_id=integ.id, exam_id=e.id, subtask_key="A1", page_id="p") for e in exams])
    db.commit()
    return user, course, exams, integ


def test_cards_cascade_with_integration_and_exam(db):
    _, _, (e1, e2), integ = setup_rows(db)
    db.delete(db.get(Exam, e1.id))
    db.commit()
    assert [c.exam_id for c in db.scalars(select(NotionCard).where(NotionCard.integration_id == integ.id))] == [e2.id]
    db.delete(db.get(Integration, integ.id))
    db.commit()
    assert not db.scalars(select(NotionCard).where(NotionCard.integration_id == integ.id)).all()
    assert db.get(NotionDatabase, integ.id) is None


def test_card_key_is_unique(db):
    _, _, (e1, _), integ = setup_rows(db)
    db.add(NotionCard(integration_id=integ.id, exam_id=e1.id, subtask_key="A1", page_id="again"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def notion_job(course, **cols):
    return Job(filename="notion", kind="notion", user_id=course.user_id, course_id=course.id, **cols)


def test_one_active_notion_job_per_course(db):
    _, course, _, _ = setup_rows(db)
    db.add_all([notion_job(course, status="done"), notion_job(course)])
    db.commit()
    db.add(notion_job(course))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.execute(delete(Job))
    db.commit()


def test_job_kind_notion_is_accepted(db):
    _, course, _, _ = setup_rows(db)
    db.add(notion_job(course, error_code="nothing_weak"))
    db.commit()
    assert db.scalars(select(Job.kind)).one() == "notion"
