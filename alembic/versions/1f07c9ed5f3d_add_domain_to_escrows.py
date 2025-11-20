"""add domain to escrows

Revision ID: 1f07c9ed5f3d
Revises: e5a5c7e3e5d5
Create Date: 2025-02-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "1f07c9ed5f3d"
down_revision = "e5a5c7e3e5d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    domain_enum = sa.Enum("private", "public", "aid", name="escrowdomain", native_enum=False)
    bind = op.get_bind()
    domain_enum.create(bind, checkfirst=True)

    op.add_column(
        "escrow_agreements",
        sa.Column(
            "domain",
            domain_enum,
            nullable=False,
            server_default="private",
        ),
    )
    op.create_index("ix_escrow_agreements_domain", "escrow_agreements", ["domain"])

    if bind and bind.dialect.name != "sqlite":
        op.alter_column("escrow_agreements", "domain", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_escrow_agreements_domain", table_name="escrow_agreements")
    op.drop_column("escrow_agreements", "domain")

    domain_enum = sa.Enum("private", "public", "aid", name="escrowdomain", native_enum=False)
    bind = op.get_bind()
    domain_enum.drop(bind, checkfirst=True)
