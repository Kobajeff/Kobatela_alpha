"""add ai review metadata to proofs

Revision ID: 1b7cc2cfcc6e
Revises: 9c697d41f421
Create Date: 2025-11-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "1b7cc2cfcc6e"
down_revision = "9c697d41f421"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proofs",
        sa.Column("ai_reviewed_by", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "proofs",
        sa.Column("ai_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_proofs_ai_reviewed_by", "proofs", ["ai_reviewed_by"])


def downgrade() -> None:
    op.drop_index("ix_proofs_ai_reviewed_by", table_name="proofs")
    op.drop_column("proofs", "ai_reviewed_at")
    op.drop_column("proofs", "ai_reviewed_by")
