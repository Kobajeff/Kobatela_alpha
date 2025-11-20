"""add user_id to api_keys

Revision ID: 5c6b0e0a17b7
Revises: 3d7e23f4c1e9
Create Date: 2025-03-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "5c6b0e0a17b7"
down_revision = "3d7e23f4c1e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_api_keys_user_id_users", "users", ["user_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.drop_constraint("fk_api_keys_user_id_users", type_="foreignkey")
        batch_op.drop_column("user_id")
