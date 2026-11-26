"""integrations (encrypted third-party tokens) and webhook_events (dedup)

Revision ID: f4a5b6c7d8e9
Revises: d3e4f5a6b7c8
Create Date: 2026-11-21 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f4a5b6c7d8e9"
down_revision: str | Sequence[str] | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "provider",
            sa.Enum("slack", "notion", name="integration_provider", native_enum=False, create_constraint=True, length=6),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("workspace_name", sa.String(), nullable=False),
        sa.Column("external_user_id", sa.String(), nullable=False),
        sa.Column("access_token", sa.String(), nullable=False),
        sa.Column("scopes", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_integrations_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_integrations"),
        sa.UniqueConstraint("provider", "workspace_id", "external_user_id", name="uq_integrations_provider_workspace_id_external_user_id"),
    )
    op.create_index("ix_integrations_user_id", "integrations", ["user_id"])
    op.create_table(
        "webhook_events",
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("provider", "event_id", name="pk_webhook_events"),
    )


def downgrade() -> None:
    op.drop_table("webhook_events")
    op.drop_index("ix_integrations_user_id", table_name="integrations")
    op.drop_table("integrations")
