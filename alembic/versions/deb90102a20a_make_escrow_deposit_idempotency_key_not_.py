"""make escrow deposit idempotency key not null

Revision ID: deb90102a20a
Revises: 1b7cc2cfcc6e
Create Date: 2025-11-19 11:23:47.156258
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "deb90102a20a"
down_revision = "1b7cc2cfcc6e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    deposits = sa.table(
        "escrow_deposits",
        sa.column("id", sa.Integer),
        sa.column("idempotency_key", sa.String(length=64)),
    )

    conn = op.get_bind()
    rows = conn.execute(sa.select(deposits.c.id, deposits.c.idempotency_key)).fetchall()
    for row_id, key in rows:
        if key is None:
            conn.execute(
                sa.update(deposits)
                .where(deposits.c.id == row_id)
                .values(idempotency_key=f"legacy|deposit:{row_id}")
            )

    with op.batch_alter_table("escrow_deposits") as batch_op:
        batch_op.alter_column(
            "idempotency_key",
            existing_type=sa.String(length=64),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("escrow_deposits") as batch_op:
        batch_op.alter_column(
            "idempotency_key",
            existing_type=sa.String(length=64),
            nullable=True,
        )
