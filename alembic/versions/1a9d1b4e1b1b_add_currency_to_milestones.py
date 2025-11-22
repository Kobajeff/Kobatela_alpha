"""Add currency to milestones

Revision ID: 1a9d1b4e1b1b
Revises: 9c697d41f421
Create Date: 2025-02-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "1a9d1b4e1b1b"
down_revision = "9c697d41f421"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "milestones",
        sa.Column("currency", sa.String(length=3), nullable=True),
    )
    op.execute("UPDATE milestones SET currency = 'USD' WHERE currency IS NULL")
    op.alter_column(
        "milestones",
        "currency",
        existing_type=sa.String(length=3),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("milestones", "currency")
