"""Adjust monetary columns and add integrity constraints"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20251109_adjust_monetary_constraints"
down_revision = "20251108_add_last_reset_allowed_payees"
branch_labels = None
depends_on = None


NUMERIC_TYPE = sa.Numeric(18, 2)


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    # Init inspecteur
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    # transactions
    if "transactions" in tables:
        with op.batch_alter_table("transactions", schema=None) as batch:
            batch.alter_column("amount", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)

    # escrow_agreements
    if "escrow_agreements" in tables:
        with op.batch_alter_table("escrow_agreements", schema=None) as batch:
            batch.alter_column("amount_total", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
            batch.create_check_constraint("ck_escrow_amount_total_non_negative", "amount_total >= 0")

        op.create_index("ix_escrow_status", "escrow_agreements", ["status"], unique=False, if_not_exists=True)
        op.create_index("ix_escrow_deadline", "escrow_agreements", ["deadline_at"], unique=False, if_not_exists=True)

    # escrow_deposits
    if "escrow_deposits" in tables:
        with op.batch_alter_table("escrow_deposits", schema=None) as batch:
            batch.alter_column("amount", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
            batch.create_check_constraint("ck_escrow_deposit_positive_amount", "amount > 0")

    # milestones
    if "milestones" in tables:
        with op.batch_alter_table("milestones", schema=None) as batch:
            batch.alter_column("amount", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
            batch.create_check_constraint("ck_milestone_positive_amount", "amount > 0")
            batch.create_check_constraint("ck_milestone_positive_idx", "idx > 0")
            batch.create_check_constraint(
                "ck_milestone_geofence_radius_non_negative",
                "geofence_radius_m IS NULL OR geofence_radius_m >= 0",
            )

    # allowed_payees
    if "allowed_payees" in tables:
        with op.batch_alter_table("allowed_payees", schema=None) as batch:
            batch.alter_column("daily_limit", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
            batch.alter_column("total_limit", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
            batch.alter_column("spent_today", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
            batch.alter_column("spent_total", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
            batch.create_check_constraint("ck_allowed_payee_daily_limit", "daily_limit IS NULL OR daily_limit >= 0")
            batch.create_check_constraint("ck_allowed_payee_total_limit", "total_limit IS NULL OR total_limit >= 0")
            batch.create_check_constraint("ck_allowed_payee_spent_today_non_negative", "spent_today >= 0")
            batch.create_check_constraint("ck_allowed_payee_spent_total_non_negative", "spent_total >= 0")

    # purchases
    if "purchases" in tables:
        with op.batch_alter_table("purchases", schema=None) as batch:
            batch.alter_column("amount", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)

    # payments
    if "payments" in tables:
        with op.batch_alter_table("payments", schema=None) as batch:
            batch.alter_column("amount", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
            batch.create_check_constraint("ck_payment_positive_amount", "amount > 0")
            batch.create_unique_constraint("uq_payments_psp_ref", ["psp_ref"])

        op.create_index("ix_payments_created_at", "payments", ["created_at"], unique=False, if_not_exists=True)
        op.create_index("ix_payments_status", "payments", ["status"], unique=False, if_not_exists=True)
        op.create_index(
            "ix_payments_escrow_status", "payments", ["escrow_id", "status"], unique=False, if_not_exists=True
        )

    # proofs
    if "proofs" in tables:
        with op.batch_alter_table("proofs", schema=None) as batch:
            batch.create_unique_constraint("uq_proofs_sha256", ["sha256"])

    # escrow_events
    if "escrow_events" in tables:
        if not _has_column("escrow_events", "idempotency_key"):
            with op.batch_alter_table("escrow_events", schema=None) as batch:
                batch.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))

        op.create_index(
            "ix_escrow_events_idempotency_key", "escrow_events", ["idempotency_key"], unique=False, if_not_exists=True
        )

    # psp_webhook_events
    if "psp_webhook_events" in tables:
        op.create_index(
            "ix_psp_webhook_events_received", "psp_webhook_events", ["received_at"], unique=False, if_not_exists=True
        )
        op.create_index(
            "ix_psp_webhook_events_kind", "psp_webhook_events", ["kind"], unique=False, if_not_exists=True
        )
