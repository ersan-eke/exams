"""jobs subject

Revision ID: 4b78faf1d92c
Revises: 973c5583a5df
Create Date: 2026-10-29 12:04:50.209266

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b78faf1d92c"
down_revision: str | Sequence[str] | None = "973c5583a5df"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("subject", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "subject")
