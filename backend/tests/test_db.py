import uuid

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import func, select, text

from app.db.exams import course_id, from_rows, to_rows
from app.db.models import Base, Course, Exam, Subtask, User
from app.pipeline import models as p

box = p.BBox(x0=0.1, y0=0.2, x1=0.9, y1=0.8)
SAMPLE = p.ExamStructure(
    source="endterm.pdf",
    page_count=2,
    page_sizes=[(595.0, 842.0), (595.0, 842.0)],
    kind="digital",
    is_solution=True,
    total_points_stated=10.5,
    duration_minutes=90,
    mc_rule=p.McRule(kind="per_tick", right=1, wrong=-0.5),
    issues=[p.Issue(level="warn", message="points don't add up")],
    tasks=[
        p.Task(
            id="A1",
            number="1",
            title="Basics",
            points=10.5,
            context=[p.Context(id="A1-ctx", regions=[p.Region(page=0, bbox=box, image="ctx.png")], text="stem")],
            subtasks=[
                p.Subtask(
                    id="A1a",
                    label="a)*",
                    points=0.5,
                    independent=True,
                    regions=[p.Region(page=0, bbox=box, image="a.png")],
                    text="question",
                    solution_text="answer",
                    mc_options=[p.McOption(region=0, bbox=box, text="yes"), p.McOption(region=0, bbox=box, text="no")],
                    mc_key=[1],
                ),
                p.Subtask(
                    id="A1b",
                    label="b)",
                    regions=[p.Region(page=0, bbox=box), p.Region(page=1, bbox=box)],
                    answer_boxes=[p.AnswerBox(region=1, bbox=box)],
                ),
            ],
        )
    ],
)


def test_migrations_match_models(db):
    assert compare_metadata(MigrationContext.configure(db.connection()), Base.metadata) == []


def test_exam_round_trip(db):
    exam_id = uuid.uuid4()
    db.add(to_rows(exam_id, SAMPLE, title="Endterm"))
    db.commit()
    db.expunge_all()
    assert from_rows(db.get(Exam, exam_id)) == SAMPLE


def test_deleting_exam_cascades_in_db(db):
    exam_id = uuid.uuid4()
    db.add(to_rows(exam_id, SAMPLE, title="Endterm"))
    db.commit()
    before = db.scalar(select(func.count()).select_from(Subtask))
    db.execute(text("DELETE FROM exams WHERE id = :id"), {"id": exam_id})  # raw SQL: the FK must cascade, not the ORM
    db.commit()
    assert db.scalar(select(func.count()).select_from(Subtask)) == before - 2


def test_course_names_fold_case(db):
    user = User(email=f"{uuid.uuid4().hex}@example.com")
    db.add(user)
    db.commit()
    first = course_id(db, user.id, "GRNVS")
    assert course_id(db, user.id, "grnvs") == first
    assert db.scalar(select(Course.name).where(Course.id == first)) == "GRNVS"
    # Python's "İ".lower() differs from Postgres lower(); both sides must fold the same way
    assert course_id(db, user.id, "İstatistik") == course_id(db, user.id, "İstatistik")
