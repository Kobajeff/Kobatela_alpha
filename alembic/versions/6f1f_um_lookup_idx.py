"""Add lookup index on usage mandates."""
from alembic import op

# revision identifiers, used by Alembic.
revision = "6f1f_um_lookup_idx"
down_revision = "5b91fcb4d6af"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_um_active_lookup",
        "usage_mandates",
        ["sender_id", "beneficiary_id", "currency", "status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_um_active_lookup", table_name="usage_mandates")
