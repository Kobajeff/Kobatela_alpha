"""Add idempotency_key to escrow_events table"""

from alembic import op
import sqlalchemy as sa

# Identifiants de migration
revision = "20251111_add_idempotency_to_escrow_events"
down_revision = "20251110_add_payment_idempotency_index"
branch_labels = None
depends_on = None


def upgrade():
    # ✅ Important : resolve_fks=False pour SQLite
    with op.batch_alter_table("escrow_events", reflect_kwargs={"resolve_fks": False}) as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))
        batch.create_index("ix_escrow_events_idempotency_key", ["idempotency_key"], unique=False)


def downgrade():
    with op.batch_alter_table("escrow_events", reflect_kwargs={"resolve_fks": False}) as batch:
        batch.drop_index("ix_escrow_events_idempotency_key")
        batch.drop_column("idempotency_key")
