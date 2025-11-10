"""Use Decimal for purchases amount column.

Revision ID: 2c2680073b35
Revises: baa4932d9a29
Create Date: 2025-11-10 15:30:57.627936
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "2c2680073b35"
down_revision = "baa4932d9a29"
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Upgrade purchases amount to store Decimal values."""

    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else ""

    numeric_type = sa.Numeric(18, 2, asdecimal=True)
    existing_type = sa.Numeric(18, 2, asdecimal=False)

    if dialect == "sqlite":
        # SQLite rebuilds the table; the Numeric definition without asdecimal hint avoids
        # round-tripping artefacts while still yielding Decimal objects via SQLAlchemy.
        numeric_type = sa.Numeric(18, 2)
        existing_type = sa.Numeric(18, 2)

    with op.batch_alter_table("purchases", schema=None) as batch_op:
        batch_op.alter_column(
            "amount",
            type_=numeric_type,
            existing_type=existing_type,
            existing_nullable=False,
        )


def downgrade() -> None:
    """Revert purchases amount to floating representation."""

    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else ""

    target_type = sa.Numeric(18, 2, asdecimal=False)
    existing_type = sa.Numeric(18, 2, asdecimal=True)

    if dialect == "sqlite":
        target_type = sa.Numeric(18, 2)
        existing_type = sa.Numeric(18, 2)

    with op.batch_alter_table("purchases", schema=None) as batch_op:
        batch_op.alter_column(
            "amount",
            type_=target_type,
            existing_type=existing_type,
            existing_nullable=False,
        )
