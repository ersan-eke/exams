"""notion: refresh token, export tables, notion jobs per course

Revision ID: a1b2c3d4e5f6
Revises: f4a5b6c7d8e9
Create Date: 2026-11-25 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "f4a5b6c7d8e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE = "kind = 'notion' AND status IN ('queued','running')"


def upgrade() -> None:
    op.add_column("integrations", sa.Column("refresh_token", sa.String(), nullable=True))
    op.create_table(
        "notion_databases",
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("database_id", sa.String(), nullable=False),
        sa.Column("data_source_id", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], name="fk_notion_databases_integration_id_integrations", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("integration_id", name="pk_notion_databases"),
    )
    op.create_table(
        "notion_cards",
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column("subtask_key", sa.String(), nullable=False),
        sa.Column("page_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], name="fk_notion_cards_integration_id_integrations", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exam_id"], ["exams.id"], name="fk_notion_cards_exam_id_exams", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("integration_id", "exam_id", "subtask_key", name="pk_notion_cards"),
    )
    op.add_column("jobs", sa.Column("course_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_jobs_course_id_courses", "jobs", "courses", ["course_id"], ["id"], ondelete="CASCADE")
    op.drop_constraint("job_kind", "jobs", type_="check")
    op.create_check_constraint("job_kind", "jobs", "kind IN ('exam', 'document', 'notion')")
    op.create_index("uq_jobs_active_notion", "jobs", ["course_id"], unique=True, postgresql_where=sa.text(ACTIVE))


def downgrade() -> None:
    op.drop_index("uq_jobs_active_notion", table_name="jobs")
    op.execute("DELETE FROM jobs WHERE kind = 'notion'")
    op.drop_constraint("job_kind", "jobs", type_="check")
    op.create_check_constraint("job_kind", "jobs", "kind IN ('exam', 'document')")
    op.drop_constraint("fk_jobs_course_id_courses", "jobs", type_="foreignkey")
    op.drop_column("jobs", "course_id")
    op.drop_table("notion_cards")
    op.drop_table("notion_databases")
    op.drop_column("integrations", "refresh_token")
