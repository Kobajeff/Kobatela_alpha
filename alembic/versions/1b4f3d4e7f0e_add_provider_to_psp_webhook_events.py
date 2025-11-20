"""Add provider to PSP webhook events and enforce provider+event_id uniqueness.

Revision ID: 1b4f3d4e7f0e
Revises: 4e1bd5489e1c
Create Date: 2025-11-27 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "1b4f3d4e7f0e"
down_revision = "4e1bd5489e1c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("psp_webhook_events") as batch_op:
        batch_op.add_column(
            sa.Column("provider", sa.String(length=50), nullable=False, server_default="default"),
        )
        batch_op.drop_constraint("uq_psp_event_id", type_="unique")
        batch_op.create_unique_constraint(
            "uq_psp_webhook_events_provider_event_id",
            ["provider", "event_id"],
        )

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.alter_column("psp_webhook_events", "provider", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("psp_webhook_events") as batch_op:
        batch_op.drop_constraint("uq_psp_webhook_events_provider_event_id", type_="unique")
        batch_op.drop_column("provider")
        batch_op.create_unique_constraint("uq_psp_event_id", ["event_id"])
