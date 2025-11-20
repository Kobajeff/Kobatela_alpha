"""change ai_score to numeric

Revision ID: c7f3d2f1fb35
Revises: 1b4f3d4e7f0e
Create Date: 2024-05-22 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c7f3d2f1fb35"
down_revision = "1b4f3d4e7f0e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("proofs") as batch_op:
        batch_op.alter_column(
            "ai_score",
            type_=sa.Numeric(4, 3),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("proofs") as batch_op:
        batch_op.alter_column(
            "ai_score",
            type_=sa.Float(),
            existing_nullable=True,
        )
