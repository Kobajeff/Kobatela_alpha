"""Add user foreign key to api_keys."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f77e6c785ac8"
down_revision = "e5a5c7e3e5d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_api_keys_user_id_users", "users", ["user_id"], ["id"])
        batch_op.create_index("ix_api_keys_user_id", ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.drop_constraint("fk_api_keys_user_id_users", type_="foreignkey")
        batch_op.drop_index("ix_api_keys_user_id")
        batch_op.drop_column("user_id")
