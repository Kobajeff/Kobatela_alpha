"""Add idempotency_key to escrow_events table (idempotent)"""

"""Add idempotency_key to escrow_events table (idempotent)"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# Alembic identifiers
revision = "20251111_add_idempotency_to_escrow_events"
down_revision = "20251110_add_payment_idempotency_index"
branch_labels = None
depends_on = None


# ---------- Helpers ----------
def _insp():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    try:
        return table_name in set(_insp().get_table_names())
    except Exception:
        return False


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    try:
        return column_name in {c["name"] for c in _insp().get_columns(table_name)}
    except Exception:
        return False


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    try:
        return index_name in {ix["name"] for ix in _insp().get_indexes(table_name)}
    except Exception:
        return False


# ---------- Migration ----------
def upgrade() -> None:
    table = "escrow_events"
    index_name = "ix_escrow_events_idempotency_key"

    if not _has_table(table):
        # Rien à faire si la table n’existe pas dans ce contexte (ex: schéma minimal de tests)
        return

    # Ajouter la colonne de façon idempotente
    if not _has_column(table, "idempotency_key"):
        with op.batch_alter_table(table, reflect_kwargs={"resolve_fks": False}) as batch:
            batch.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))

    # Créer l’index si absent
    if not _has_index(table, index_name):
        # if_not_exists est supporté par Alembic récents; on garde tout de même notre garde-fou ci-dessus
        op.create_index(index_name, table, ["idempotency_key"], unique=False, if_not_exists=True)


def downgrade() -> None:
    table = "escrow_events"
    index_name = "ix_escrow_events_idempotency_key"

    if not _has_table(table):
        return

    # Drop l’index s’il existe
    if _has_index(table, index_name):
        op.drop_index(index_name, table_name=table)

    # Drop la colonne s’il elle existe
    if _has_column(table, "idempotency_key"):
        with op.batch_alter_table(table, reflect_kwargs={"resolve_fks": False}) as batch:
            batch.drop_column("idempotency_key")
