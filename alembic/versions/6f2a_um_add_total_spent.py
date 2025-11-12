"""Add total_spent column to usage mandates."""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "6f2a_um_add_total_spent"
down_revision = "6f1f_um_lookup_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("usage_mandates")}

    if "total_spent" not in columns:
        op.add_column(
            "usage_mandates",
            sa.Column(
                "total_spent",
                sa.Numeric(18, 2, asdecimal=True),
                nullable=False,
                server_default="0.00",
            ),
        )

    if bind.dialect.name != "sqlite":
        op.alter_column(
            "usage_mandates",
            "total_spent",
            server_default=None,
        )


def downgrade() -> None:
    op.drop_column("usage_mandates", "total_spent")
