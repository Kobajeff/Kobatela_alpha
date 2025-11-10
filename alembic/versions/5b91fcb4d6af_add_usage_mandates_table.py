"""Add usage mandates table.

Revision ID: 5b91fcb4d6af
Revises: 2c2680073b35
Create Date: 2025-11-10 16:45:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "5b91fcb4d6af"
down_revision = "2c2680073b35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status_enum = sa.Enum("ACTIVE", "EXPIRED", "CONSUMED", name="usage_mandate_status")
    bind = op.get_bind()
    status_enum.create(bind, checkfirst=True)

    op.create_table(
        "usage_mandates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "sender_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "beneficiary_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("total_amount", sa.Numeric(18, 2, asdecimal=True), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column(
            "allowed_category_id",
            sa.Integer(),
            sa.ForeignKey("spend_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "allowed_merchant_id",
            sa.Integer(),
            sa.ForeignKey("merchants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", status_enum, nullable=False, server_default="ACTIVE"),
        sa.CheckConstraint("total_amount >= 0", name="ck_usage_mandate_non_negative"),
    )
    op.create_index(
        "ix_usage_mandates_sender_id", "usage_mandates", ["sender_id"], unique=False
    )
    op.create_index(
        "ix_usage_mandates_beneficiary_id", "usage_mandates", ["beneficiary_id"], unique=False
    )
    op.create_index(
        "ix_usage_mandates_allowed_category_id",
        "usage_mandates",
        ["allowed_category_id"],
        unique=False,
    )
    op.create_index(
        "ix_usage_mandates_allowed_merchant_id",
        "usage_mandates",
        ["allowed_merchant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_usage_mandates_allowed_merchant_id", table_name="usage_mandates")
    op.drop_index("ix_usage_mandates_allowed_category_id", table_name="usage_mandates")
    op.drop_index("ix_usage_mandates_beneficiary_id", table_name="usage_mandates")
    op.drop_index("ix_usage_mandates_sender_id", table_name="usage_mandates")
    op.drop_table("usage_mandates")

    status_enum = sa.Enum("ACTIVE", "EXPIRED", "CONSUMED", name="usage_mandate_status")
    bind = op.get_bind()
    status_enum.drop(bind, checkfirst=True)
