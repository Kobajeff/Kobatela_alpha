"""add api_keys table

Revision ID: 8b7e_add_api_keys
Revises: 6f2a_um_add_total_spent
Create Date: 2025-11-12
"""

from alembic import op
import sqlalchemy as sa


revision = "8b7e_add_api_keys"
down_revision = "6f2a_um_add_total_spent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("key", sa.String(length=128), nullable=False, unique=True),
        sa.Column(
            "scope",
            sa.Enum("sender", "support", "admin", name="apiscope"),
            nullable=False,
            server_default="sender",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("key", name="uq_api_keys_key"),
    )


def downgrade() -> None:
    op.drop_table("api_keys")
    sa.Enum(name="apiscope").drop(op.get_bind(), checkfirst=False)
