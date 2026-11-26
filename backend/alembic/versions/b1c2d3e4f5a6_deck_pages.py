"""deck pages: printed label, title, section, headings and cleaned text per Deck page

Revision ID: b1c2d3e4f5a6
Revises: a9f3c1d2e4b6
Create Date: 2026-11-14 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | Sequence[str] | None = "a9f3c1d2e4b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deck_pages",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("section", sa.String(), nullable=False),
        sa.Column("headings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], name=op.f("fk_deck_pages_document_id_documents"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("document_id", "page", name=op.f("pk_deck_pages")),
    )


def downgrade() -> None:
    op.drop_table("deck_pages")
