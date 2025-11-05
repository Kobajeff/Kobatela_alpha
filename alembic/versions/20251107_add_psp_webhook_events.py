"""add PSP webhook events table"""
from alembic import op
import sqlalchemy as sa

revision = "20251107_add_psp_webhook_events"
down_revision = "20251106_add_allowed_payees"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "psp_webhook_events" in inspector.get_table_names():
        return

    op.create_table(
        "psp_webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(length=100), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("psp_ref", sa.String(length=100), nullable=True),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("raw_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("event_id", name="uq_psp_event_id"),
    )


def downgrade() -> None:
    op.drop_table("psp_webhook_events")
