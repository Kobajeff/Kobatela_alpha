"""Create api_keys table."""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "7a3b_api_keys_table"
down_revision = "6f2a_um_add_total_spent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("prefix", sa.String(length=12), nullable=False),
        sa.Column("key_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column(
            "scope",
            sa.Enum("sender", "support", "admin", name="apiscope"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("prefix", name="uq_api_keys_prefix"),
    )


def downgrade() -> None:
    op.drop_table("api_keys")
    op.execute("DROP TYPE IF EXISTS apiscope")
