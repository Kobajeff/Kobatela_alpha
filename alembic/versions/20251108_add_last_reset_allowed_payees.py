"""add last_reset_at to allowed payees"""
from alembic import op
import sqlalchemy as sa


revision = "20251108_add_last_reset_allowed_payees"
down_revision = "20251107_add_psp_webhook_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("allowed_payees")}
    if "last_reset_at" not in columns:
        op.add_column("allowed_payees", sa.Column("last_reset_at", sa.Date(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("allowed_payees")}
    if "last_reset_at" in columns:
        op.drop_column("allowed_payees", "last_reset_at")
