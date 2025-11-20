"""add public_tag to users

Revision ID: e5a5c7e3e5d5
Revises: c7f3d2f1fb35
Create Date: 2025-02-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e5a5c7e3e5d5"
down_revision = "c7f3d2f1fb35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "public_tag",
            sa.String(length=10),
            nullable=False,
            server_default="private",
        ),
    )
    op.create_index("ix_users_public_tag", "users", ["public_tag"])

    bind = op.get_bind()
    if bind and bind.dialect.name != "sqlite":
        op.alter_column("users", "public_tag", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_users_public_tag", table_name="users")
    op.drop_column("users", "public_tag")
