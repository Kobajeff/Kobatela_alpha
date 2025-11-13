"""Ensure unique active usage mandates per sender/beneficiary/currency."""

from alembic import op

# revision identifiers, used by Alembic.
revision = "7a4c_unique_active_mandate"
down_revision = "8b7e_add_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_usage_mandate_active
    ON usage_mandates(sender_id, beneficiary_id, currency)
    WHERE status = 'ACTIVE'
    """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_usage_mandate_active")
