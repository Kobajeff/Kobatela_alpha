"""add AI advisor fields to proofs

Revision ID: 013024e16da9
Revises: 8b7e_add_api_keys
Create Date: 2025-11-17 12:37:48.220422
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "013024e16da9"
down_revision = "8b7e_add_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proofs",
        sa.Column("ai_risk_level", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "proofs",
        sa.Column("ai_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "proofs",
        sa.Column("ai_flags", sa.JSON(), nullable=True),
    )
    op.add_column(
        "proofs",
        sa.Column("ai_explanation", sa.Text(), nullable=True),
    )
    op.add_column(
        "proofs",
        sa.Column("ai_checked_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_proofs_ai_risk_level",
        "proofs",
        ["ai_risk_level"],
    )


def downgrade() -> None:
    op.drop_index("ix_proofs_ai_risk_level", table_name="proofs")
    op.drop_column("proofs", "ai_checked_at")
    op.drop_column("proofs", "ai_explanation")
    op.drop_column("proofs", "ai_flags")
    op.drop_column("proofs", "ai_score")
    op.drop_column("proofs", "ai_risk_level")
