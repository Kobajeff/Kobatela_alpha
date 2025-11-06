"""Adjust monetary columns and add integrity constraints"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20251109_adjust_monetary_constraints"
down_revision = "20251108_add_last_reset_allowed_payees"
branch_labels = None
depends_on = None


NUMERIC_TYPE = sa.Numeric(18, 2)


def upgrade() -> None:
    with op.batch_alter_table("transactions", schema=None) as batch:
        batch.alter_column("amount", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)

    with op.batch_alter_table("escrow_agreements", schema=None) as batch:
        batch.alter_column(
            "amount_total", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE
        )
        batch.create_check_constraint(
            "ck_escrow_amount_total_non_negative", "amount_total >= 0"
        )

    op.create_index("ix_escrow_status", "escrow_agreements", ["status"], unique=False)
    op.create_index("ix_escrow_deadline", "escrow_agreements", ["deadline_at"], unique=False)

    with op.batch_alter_table("escrow_deposits", schema=None) as batch:
        batch.alter_column("amount", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
        batch.create_check_constraint("ck_escrow_deposit_positive_amount", "amount > 0")

    with op.batch_alter_table("milestones", schema=None) as batch:
        batch.alter_column("amount", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
        batch.create_check_constraint("ck_milestone_positive_amount", "amount > 0")
        batch.create_check_constraint("ck_milestone_positive_idx", "idx > 0")
        batch.create_check_constraint(
            "ck_milestone_geofence_radius_non_negative",
            "geofence_radius_m IS NULL OR geofence_radius_m >= 0",
        )

    with op.batch_alter_table("allowed_payees", schema=None) as batch:
        batch.alter_column("daily_limit", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
        batch.alter_column("total_limit", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
        batch.alter_column("spent_today", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
        batch.alter_column("spent_total", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
        batch.create_check_constraint(
            "ck_allowed_payee_daily_limit", "daily_limit IS NULL OR daily_limit >= 0"
        )
        batch.create_check_constraint(
            "ck_allowed_payee_total_limit", "total_limit IS NULL OR total_limit >= 0"
        )
        batch.create_check_constraint(
            "ck_allowed_payee_spent_today_non_negative", "spent_today >= 0"
        )
        batch.create_check_constraint(
            "ck_allowed_payee_spent_total_non_negative", "spent_total >= 0"
        )

    with op.batch_alter_table("purchases", schema=None) as batch:
        batch.alter_column("amount", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)

    with op.batch_alter_table("payments", schema=None) as batch:
        batch.alter_column("amount", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
        batch.create_check_constraint("ck_payment_positive_amount", "amount > 0")
        batch.create_unique_constraint("uq_payments_psp_ref", ["psp_ref"])

    op.create_index("ix_payments_created_at", "payments", ["created_at"], unique=False)
    op.create_index("ix_payments_status", "payments", ["status"], unique=False)
    op.create_index(
        "ix_payments_escrow_status", "payments", ["escrow_id", "status"], unique=False
    )

    with op.batch_alter_table("proofs", schema=None) as batch:
        batch.create_unique_constraint("uq_proofs_sha256", ["sha256"])

    op.create_index(
        "ix_psp_webhook_events_received",
        "psp_webhook_events",
        ["received_at"],
        unique=False,
    )
    op.create_index(
        "ix_psp_webhook_events_kind",
        "psp_webhook_events",
        ["kind"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_psp_webhook_events_kind", table_name="psp_webhook_events")
    op.drop_index("ix_psp_webhook_events_received", table_name="psp_webhook_events")

    with op.batch_alter_table("proofs", schema=None) as batch:
        batch.drop_constraint("uq_proofs_sha256", type_="unique")

    op.drop_index("ix_payments_escrow_status", table_name="payments")
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_created_at", table_name="payments")

    with op.batch_alter_table("payments", schema=None) as batch:
        batch.drop_constraint("uq_payments_psp_ref", type_="unique")
        batch.drop_constraint("ck_payment_positive_amount", type_="check")
        batch.alter_column("amount", type_=sa.Float(asdecimal=False))

    with op.batch_alter_table("purchases", schema=None) as batch:
        batch.alter_column("amount", type_=sa.Float(asdecimal=False))

    with op.batch_alter_table("allowed_payees", schema=None) as batch:
        batch.drop_constraint("ck_allowed_payee_spent_total_non_negative", type_="check")
        batch.drop_constraint("ck_allowed_payee_spent_today_non_negative", type_="check")
        batch.drop_constraint("ck_allowed_payee_total_limit", type_="check")
        batch.drop_constraint("ck_allowed_payee_daily_limit", type_="check")
        batch.alter_column("spent_total", type_=sa.Float(asdecimal=False))
        batch.alter_column("spent_today", type_=sa.Float(asdecimal=False))
        batch.alter_column("total_limit", type_=sa.Float(asdecimal=False))
        batch.alter_column("daily_limit", type_=sa.Float(asdecimal=False))

    with op.batch_alter_table("milestones", schema=None) as batch:
        batch.drop_constraint("ck_milestone_geofence_radius_non_negative", type_="check")
        batch.drop_constraint("ck_milestone_positive_idx", type_="check")
        batch.drop_constraint("ck_milestone_positive_amount", type_="check")
        batch.alter_column("amount", type_=sa.Float(asdecimal=False))

    with op.batch_alter_table("escrow_deposits", schema=None) as batch:
        batch.drop_constraint("ck_escrow_deposit_positive_amount", type_="check")
        batch.alter_column("amount", type_=sa.Float(asdecimal=False))

    op.drop_index("ix_escrow_deadline", table_name="escrow_agreements")
    op.drop_index("ix_escrow_status", table_name="escrow_agreements")

    with op.batch_alter_table("escrow_agreements", schema=None) as batch:
        batch.drop_constraint("ck_escrow_amount_total_non_negative", type_="check")
        batch.alter_column("amount_total", type_=sa.Float(asdecimal=False))

    with op.batch_alter_table("transactions", schema=None) as batch:
        batch.alter_column("amount", type_=sa.Float(asdecimal=False))
