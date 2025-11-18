"""add proof requirements to milestones

Revision ID: 9c697d41f421
Revises: 013024e16da9
Create Date: 2025-11-17 16:09:50.470957
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9c697d41f421"
down_revision = "013024e16da9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "milestones",
        sa.Column("proof_requirements", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("milestones", "proof_requirements")
