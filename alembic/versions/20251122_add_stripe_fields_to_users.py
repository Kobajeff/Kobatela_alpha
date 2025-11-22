"""Add Stripe payout fields to users

Revision ID: add_stripe_fields_to_users
Revises: 1a9d1b4e1b1b
Create Date: 2025-11-22
"""

from alembic import op
import sqlalchemy as sa

revision = "add_stripe_fields_to_users"
down_revision = "1a9d1b4e1b1b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("stripe_account_id", sa.String(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "stripe_payout_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column("users", sa.Column("stripe_payout_status", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "stripe_payout_status")
    op.drop_column("users", "stripe_payout_enabled")
    op.drop_column("users", "stripe_account_id")
