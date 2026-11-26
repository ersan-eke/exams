"""sync

Revision ID: 2c1ca18c29ed
Revises: e7a1c2d3b4f5
Create Date: 2026-11-03 00:18:22.050702

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2c1ca18c29ed"
down_revision: str | Sequence[str] | None = "e7a1c2d3b4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("attempts", sa.Column("overtime", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("attempts", sa.Column("edited_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.drop_constraint(op.f("uq_courses_user_id_name"), "courses", type_="unique")
    # merge courses that only differ in case into the oldest one, or the unique index below fails
    # shortcut: courses has no created_at, so "oldest" is the lowest ctid (insertion order on a table that is never updated)
    op.execute("""
        CREATE TEMP TABLE course_keep ON COMMIT DROP AS
        SELECT id, first_value(id) OVER (PARTITION BY user_id, lower(name) ORDER BY ctid) AS keep FROM courses
    """)
    op.execute("UPDATE exams SET course_id = k.keep FROM course_keep k WHERE exams.course_id = k.id AND k.id <> k.keep")
    op.execute("DELETE FROM courses USING course_keep k WHERE courses.id = k.id AND k.id <> k.keep")
    op.create_index("ix_courses_user_lower_name", "courses", ["user_id", sa.literal_column("lower(name)")], unique=True)
    op.add_column("exams", sa.Column("point_overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("exams", sa.Column("rubrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("exams", sa.Column("solution_for", sa.Uuid(), nullable=True))
    op.add_column("exams", sa.Column("fingerprint", sa.String(), nullable=True))
    op.add_column("exams", sa.Column("edited_at", sa.DateTime(timezone=True), server_default=sa.text("to_timestamp(0)"), nullable=False))
    op.add_column("grades", sa.Column("llm", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("grades", "llm")
    op.drop_column("exams", "edited_at")
    op.drop_column("exams", "fingerprint")
    op.drop_column("exams", "solution_for")
    op.drop_column("exams", "rubrics")
    op.drop_column("exams", "point_overrides")
    op.drop_index("ix_courses_user_lower_name", table_name="courses")
    op.create_unique_constraint(op.f("uq_courses_user_id_name"), "courses", ["user_id", "name"], postgresql_nulls_not_distinct=False)
    op.drop_column("attempts", "edited_at")
    op.drop_column("attempts", "overtime")
