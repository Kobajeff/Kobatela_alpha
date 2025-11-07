from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "20251110_add_payment_idempotency_index"
down_revision = "20251109_adjust_monetary_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    tables = set(insp.get_table_names())
    if "payments" not in tables:
        # Rien à faire si la table n'existe pas (ex: base partielle en dev)
        return

    # Si l’index existe déjà, ne rien faire (idempotent)
    existing = {ix["name"] for ix in insp.get_indexes("payments")}
    if "ix_payments_idempotency_key" not in existing:
        op.create_index(
            "ix_payments_idempotency_key",
            "payments",
            ["idempotency_key"],
            unique=False,
            if_not_exists=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if "payments" in set(insp.get_table_names()):
        # drop sans crash si absent
        try:
            op.drop_index("ix_payments_idempotency_key", table_name="payments")
        except Exception:
            pass


