"""Add idempotency_key to escrow_events table (idempotent)"""

from alembic import op
import sqlalchemy as sa

revision = "20251111_add_idempotency_to_escrow_events"
down_revision = "20251110_add_payment_idempotency_index"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in [c["name"] for c in insp.get_columns(table)]


def _has_index(table: str, index_name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return index_name in [ix["name"] for ix in insp.get_indexes(table)]


def upgrade():
    index_name = "ix_escrow_events_idempotency_key"
    with op.batch_alter_table(
        "escrow_events", reflect_kwargs={"resolve_fks": False}
    ) as batch:
        if not _has_column("escrow_events", "idempotency_key"):
            batch.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))
        if not _has_index("escrow_events", index_name):
            batch.create_index(index_name, ["idempotency_key"], unique=False)


def downgrade():
    index_name = "ix_escrow_events_idempotency_key"
    with op.batch_alter_table(
        "escrow_events", reflect_kwargs={"resolve_fks": False}
    ) as batch:
        if _has_index("escrow_events", index_name):
            batch.drop_index(index_name)
        if _has_column("escrow_events", "idempotency_key"):
            batch.drop_column("idempotency_key")
