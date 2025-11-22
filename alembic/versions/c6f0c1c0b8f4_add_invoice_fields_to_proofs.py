"""Add invoice fields to proofs."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c6f0c1c0b8f4_add_invoice_fields_to_proofs"
down_revision = "a9bba28305c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add invoice_total_amount and invoice_currency columns."""

    op.add_column(
        "proofs",
        sa.Column(
            "invoice_total_amount",
            sa.Numeric(18, 2, asdecimal=True),
            nullable=True,
        ),
    )
    op.add_column(
        "proofs",
        sa.Column(
            "invoice_currency",
            sa.String(length=3),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove invoice columns from proofs."""

    op.drop_column("proofs", "invoice_currency")
    op.drop_column("proofs", "invoice_total_amount")
