"""add scheduler locks table

Revision ID: a9bba28305c0
Revises: deb90102a20a
Create Date: 2025-11-19 11:25:51.467680
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a9bba28305c0"
down_revision = "deb90102a20a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduler_locks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("scheduler_locks")
