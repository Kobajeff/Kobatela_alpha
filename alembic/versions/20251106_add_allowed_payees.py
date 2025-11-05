"""add allowed payees table"""
from alembic import op
import sqlalchemy as sa

revision = "20251106_add_allowed_payees"
down_revision = "20251105_add_geofence_to_milestones"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "allowed_payees" in inspector.get_table_names():
        return

    op.create_table(
        "allowed_payees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("escrow_id", sa.Integer(), sa.ForeignKey("escrow_agreements.id"), nullable=False),
        sa.Column("payee_ref", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("daily_limit", sa.Float(), nullable=True),
        sa.Column("total_limit", sa.Float(), nullable=True),
        sa.Column("spent_today", sa.Float(), nullable=False, server_default="0"),
        sa.Column("spent_total", sa.Float(), nullable=False, server_default="0"),
        sa.UniqueConstraint("escrow_id", "payee_ref", name="uq_allowed_payee_ref"),
    )
    op.create_index("ix_allowed_payees_escrow_id", "allowed_payees", ["escrow_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "allowed_payees" not in inspector.get_table_names():
        return

    op.drop_index("ix_allowed_payees_escrow_id", table_name="allowed_payees")
    op.drop_table("allowed_payees")
