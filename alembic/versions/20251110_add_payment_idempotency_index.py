"""Add index on payments.idempotency_key."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251110_add_payment_idempotency_index"
down_revision = "20251109_adjust_monetary_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes("payments")}
    if "ix_payments_idempotency_key" not in existing_indexes:
        op.create_index(
            "ix_payments_idempotency_key",
            "payments",
            ["idempotency_key"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes("payments")}
    if "ix_payments_idempotency_key" in existing_indexes:
        op.drop_index("ix_payments_idempotency_key", table_name="payments")
