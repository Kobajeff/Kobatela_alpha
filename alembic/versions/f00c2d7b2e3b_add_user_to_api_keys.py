"""Add user reference to api_keys"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f00c2d7b2e3b"
down_revision = "3d7e23f4c1e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("api_keys", "user_id")
