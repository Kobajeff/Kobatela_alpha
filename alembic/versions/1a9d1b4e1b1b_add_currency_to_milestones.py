"""Add currency to milestones

Revision ID: 1a9d1b4e1b1b
Revises: f00c2d7b2e3b
Create Date: 2025-02-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "1a9d1b4e1b1b"
down_revision = "3cf2f7c1d4be"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "milestones",
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=True,
            server_default=sa.text("'USD'"),
        ),
    )
    op.execute("UPDATE milestones SET currency = 'USD' WHERE currency IS NULL")

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("milestones") as batch_op:
            batch_op.alter_column(
                "currency",
                existing_type=sa.String(length=3),
                nullable=False,
            )
    else:
        op.alter_column(
            "milestones",
            "currency",
            existing_type=sa.String(length=3),
            nullable=False,
        )


def downgrade() -> None:
    op.drop_column("milestones", "currency")
