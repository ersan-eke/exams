"""task mc_rule

Revision ID: e7a1c2d3b4f5
Revises: 4b78faf1d92c
Create Date: 2026-11-01 17:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7a1c2d3b4f5"
down_revision: str | Sequence[str] | None = "4b78faf1d92c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("mc_rule", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "mc_rule")
