"""rag: documents, chunks, document jobs

Revision ID: a9f3c1d2e4b6
Revises: 7cea61f142c4
Create Date: 2026-11-05 10:00:00

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a9f3c1d2e4b6"
down_revision: str | Sequence[str] | None = "7cea61f142c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.Enum("slides", "script", "exercises", name="document_kind", native_enum=False, create_constraint=True), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_documents_user_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], name=op.f("fk_documents_course_id_courses"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("user_id", "sha256", name=op.f("uq_documents_user_id_sha256")),
    )
    op.create_index(op.f("ix_documents_user_id"), "documents", ["user_id"])
    op.create_index(op.f("ix_documents_course_id"), "documents", ["course_id"])
    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("subtask_id", sa.Integer(), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("tsv", postgresql.TSVECTOR(), sa.Computed("to_tsvector('simple', text)", persisted=True), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(384), nullable=False),
        sa.CheckConstraint("(document_id IS NULL) <> (subtask_id IS NULL)", name=op.f("ck_chunks_owner")),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], name=op.f("fk_chunks_document_id_documents"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subtask_id"], ["subtasks.id"], name=op.f("fk_chunks_subtask_id_subtasks"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
    )
    op.create_index(op.f("ix_chunks_document_id"), "chunks", ["document_id"])
    op.create_index(op.f("ix_chunks_subtask_id"), "chunks", ["subtask_id"])
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")
    op.create_index("ix_chunks_embedding", "chunks", ["embedding"], postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"})

    op.add_column(
        "jobs",
        sa.Column(
            "kind", sa.Enum("exam", "document", name="job_kind", native_enum=False, create_constraint=True), server_default="exam", nullable=False
        ),
    )
    op.add_column("jobs", sa.Column("document_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(op.f("fk_jobs_document_id_documents"), "jobs", "documents", ["document_id"], ["id"], ondelete="SET NULL")
    op.alter_column("jobs", "role", existing_type=sa.String(), nullable=True)  # document jobs have no role; the CHECK ignores NULL


def downgrade() -> None:
    op.execute("DELETE FROM jobs WHERE role IS NULL")
    op.alter_column("jobs", "role", existing_type=sa.String(), nullable=False)
    op.drop_constraint(op.f("fk_jobs_document_id_documents"), "jobs", type_="foreignkey")
    op.drop_column("jobs", "document_id")
    op.drop_column("jobs", "kind")
    op.drop_table("chunks")
    op.drop_table("documents")
