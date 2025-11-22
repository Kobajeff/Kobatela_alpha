"""Add fundings table.

Revision ID: 3cf2f7c1d4be
Revises: f00c2d7b2e3b
Create Date: 2024-07-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "3cf2f7c1d4be"
down_revision = "f00c2d7b2e3b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    funding_status_enum = sa.Enum("CREATED", "SUCCEEDED", "FAILED", name="fundingstatus")
    bind = op.get_bind()
    funding_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "fundings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("escrow_id", sa.Integer(), sa.ForeignKey("escrow_agreements.id"), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(length=128), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2, asdecimal=True), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            funding_status_enum,
            nullable=False,
            server_default="CREATED",
        ),
        sa.UniqueConstraint(
            "stripe_payment_intent_id", name="uq_fundings_stripe_payment_intent_id"
        ),
    )
    op.create_index("ix_fundings_escrow_id", "fundings", ["escrow_id"], unique=False)
    op.create_index("ix_fundings_status", "fundings", ["status"], unique=False)
    op.create_index("ix_fundings_created_at", "fundings", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_fundings_created_at", table_name="fundings")
    op.drop_index("ix_fundings_status", table_name="fundings")
    op.drop_index("ix_fundings_escrow_id", table_name="fundings")
    op.drop_table("fundings")

    funding_status_enum = sa.Enum("CREATED", "SUCCEEDED", "FAILED", name="fundingstatus")
    bind = op.get_bind()
    funding_status_enum.drop(bind, checkfirst=True)
