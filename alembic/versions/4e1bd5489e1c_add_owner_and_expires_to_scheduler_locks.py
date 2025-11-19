"""Add owner and expires_at to scheduler locks

Revision ID: 4e1bd5489e1c
Revises: a9bba28305c0
Create Date: 2025-11-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "4e1bd5489e1c"
down_revision = "c6f0c1c0b8f4_add_invoice_fields_to_proofs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scheduler_locks",
        sa.Column("owner", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "scheduler_locks",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scheduler_locks", "expires_at")
    op.drop_column("scheduler_locks", "owner")
