"""Adjust monetary columns and add integrity constraints"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "20251109_adjust_monetary_constraints"
down_revision = "20251108_add_last_reset_allowed_payees"
branch_labels = None
depends_on = None

NUMERIC_TYPE = sa.Numeric(18, 2)

def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return table_name in set(insp.get_table_names())
    except Exception:
        return False


def _drop_batch_tmp(table: str) -> None:
    # Nettoie les tables temporaires laissées par un batch interrompu (SQLite)
    op.execute(text(f"DROP TABLE IF EXISTS _alembic_tmp_{table}"))


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}

def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return index_name in {idx["name"] for idx in insp.get_indexes(table_name)}
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    # Désactiver les FK pendant les batch copies SQLite
    op.execute(text("PRAGMA foreign_keys=OFF"))

    try:
        # transactions
        if "transactions" in tables:
            _drop_batch_tmp("transactions")
            with op.batch_alter_table(
                "transactions", schema=None, reflect_kwargs={"resolve_fks": False}
            ) as batch:
                batch.alter_column("amount", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)

        # escrow_agreements
        if "escrow_agreements" in tables:
            _drop_batch_tmp("escrow_agreements")
            with op.batch_alter_table(
                "escrow_agreements", schema=None, reflect_kwargs={"resolve_fks": False}
            ) as batch:
                batch.alter_column("amount_total", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
                batch.create_check_constraint("ck_escrow_amount_total_non_negative", "amount_total >= 0")

            op.create_index("ix_escrow_status", "escrow_agreements", ["status"], unique=False, if_not_exists=True)
            op.create_index("ix_escrow_deadline", "escrow_agreements", ["deadline_at"], unique=False, if_not_exists=True)

        # escrow_deposits
        if "escrow_deposits" in tables:
            _drop_batch_tmp("escrow_deposits")
            with op.batch_alter_table(
                "escrow_deposits", schema=None, reflect_kwargs={"resolve_fks": False}
            ) as batch:
                batch.alter_column("amount", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
                batch.create_check_constraint("ck_escrow_deposit_positive_amount", "amount > 0")

        # milestones
        if "milestones" in tables:
            _drop_batch_tmp("milestones")
            with op.batch_alter_table(
                "milestones", schema=None, reflect_kwargs={"resolve_fks": False}
            ) as batch:
                batch.alter_column("amount", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)
                batch.create_check_constraint("ck_milestone_positive_amount", "amount > 0")
                batch.create_check_constraint("ck_milestone_positive_idx", "idx > 0")
                batch.create_check_constraint(
                    "ck_milestone_geofence_radius_non_negative",
                    "geofence_radius_m IS NULL OR geofence_radius_m >= 0",
                )

        # allowed_payees
        if "allowed_payees" in tables:
            _drop_batch_tmp("allowed_payees")
            with op.batch_alter_table(
                "allowed_payees", schema=None, reflect_kwargs={"resolve_fks": False}
            ) as batch:
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
            _drop_batch_tmp("purchases")
            with op.batch_alter_table(
                "purchases", schema=None, reflect_kwargs={"resolve_fks": False}
            ) as batch:
                batch.alter_column("amount", existing_type=sa.Float(asdecimal=False), type_=NUMERIC_TYPE)

        # payments
        if "payments" in tables:
            _drop_batch_tmp("payments")
            with op.batch_alter_table(
                "payments", schema=None, reflect_kwargs={"resolve_fks": False}
            ) as batch:
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
            _drop_batch_tmp("proofs")
            with op.batch_alter_table(
                "proofs", schema=None, reflect_kwargs={"resolve_fks": False}
            ) as batch:
                batch.create_unique_constraint("uq_proofs_sha256", ["sha256"])

        # escrow_events
        if "escrow_events" in tables:
            _drop_batch_tmp("escrow_events")
            if not _has_column("escrow_events", "idempotency_key"):
                with op.batch_alter_table(
                    "escrow_events", schema=None, reflect_kwargs={"resolve_fks": False}
                ) as batch:
                    batch.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))

            op.create_index(
                "ix_escrow_events_idempotency_key",
                "escrow_events",
                ["idempotency_key"],
                unique=False,
                if_not_exists=True,
            )

        # psp_webhook_events
        if "psp_webhook_events" in tables:
            op.create_index(
                "ix_psp_webhook_events_received",
                "psp_webhook_events",
                ["received_at"],
                unique=False,
                if_not_exists=True,
            )
            op.create_index(
                "ix_psp_webhook_events_kind",
                "psp_webhook_events",
                ["kind"],
                unique=False,
                if_not_exists=True,
            )

    finally:
        # Réactiver les FK
        op.execute(text("PRAGMA foreign_keys=ON"))


def downgrade() -> None:
    # Couper les FK pendant le rollback aussi (SQLite)
    op.execute(text("PRAGMA foreign_keys=OFF"))
    try:
        # escrow_events — index optionnel
        if _index_exists("escrow_events", "ix_escrow_events_idempotency_key"):
            op.drop_index("ix_escrow_events_idempotency_key", table_name="escrow_events")

        # psp_webhook_events — indices optionnels
        if _index_exists("psp_webhook_events", "ix_psp_webhook_events_kind"):
            op.drop_index("ix_psp_webhook_events_kind", table_name="psp_webhook_events")
        if _index_exists("psp_webhook_events", "ix_psp_webhook_events_received"):
            op.drop_index("ix_psp_webhook_events_received", table_name="psp_webhook_events")

        # payments — indices optionnels (déjà protégés ci-dessus si tu les gardes)
        if _index_exists("payments", "ix_payments_escrow_status"):
            op.drop_index("ix_payments_escrow_status", table_name="payments")
        if _index_exists("payments", "ix_payments_status"):
            op.drop_index("ix_payments_status", table_name="payments")
        if _index_exists("payments", "ix_payments_created_at"):
            op.drop_index("ix_payments_created_at", table_name="payments")

        # proofs — ne toucher que si la table existe
        if _table_exists("proofs"):
            with op.batch_alter_table("proofs", schema=None, reflect_kwargs={"resolve_fks": False}) as batch:
                try:
                    batch.drop_constraint("uq_proofs_sha256", type_="unique")
                except Exception:
                    pass

        # escrow_events — drop colonne uniquement si table ET colonne
        if _table_exists("escrow_events") and _has_column("escrow_events", "idempotency_key"):
            with op.batch_alter_table("escrow_events", schema=None, reflect_kwargs={"resolve_fks": False}) as batch:
                batch.drop_column("idempotency_key")

        # payments — revert types + contraintes si la table existe
        if _table_exists("payments"):
            with op.batch_alter_table("payments", schema=None, reflect_kwargs={"resolve_fks": False}) as batch:
                for c in ("uq_payments_psp_ref", "ck_payment_positive_amount"):
                    try:
                        batch.drop_constraint(c, type_="unique" if c.startswith("uq_") else "check")
                    except Exception:
                        pass
                batch.alter_column("amount", type_=sa.Float(asdecimal=False))

        # purchases
        if _table_exists("purchases"):
            with op.batch_alter_table("purchases", schema=None, reflect_kwargs={"resolve_fks": False}) as batch:
                batch.alter_column("amount", type_=sa.Float(asdecimal=False))

        # allowed_payees
        if _table_exists("allowed_payees"):
            with op.batch_alter_table("allowed_payees", schema=None, reflect_kwargs={"resolve_fks": False}) as batch:
                for ck in (
                    "ck_allowed_payee_spent_total_non_negative",
                    "ck_allowed_payee_spent_today_non_negative",
                    "ck_allowed_payee_total_limit",
                    "ck_allowed_payee_daily_limit",
                ):
                    try:
                        batch.drop_constraint(ck, type_="check")
                    except Exception:
                        pass
                batch.alter_column("spent_total", type_=sa.Float(asdecimal=False))
                batch.alter_column("spent_today", type_=sa.Float(asdecimal=False))
                batch.alter_column("total_limit", type_=sa.Float(asdecimal=False))
                batch.alter_column("daily_limit", type_=sa.Float(asdecimal=False))

        # milestones
        if _table_exists("milestones"):
            with op.batch_alter_table("milestones", schema=None, reflect_kwargs={"resolve_fks": False}) as batch:
                for ck in (
                    "ck_milestone_geofence_radius_non_negative",
                    "ck_milestone_positive_idx",
                    "ck_milestone_positive_amount",
                ):
                    try:
                        batch.drop_constraint(ck, type_="check")
                    except Exception:
                        pass
                batch.alter_column("amount", type_=sa.Float(asdecimal=False))

        # escrow_deposits
        if _table_exists("escrow_deposits"):
            with op.batch_alter_table("escrow_deposits", schema=None, reflect_kwargs={"resolve_fks": False}) as batch:
                try:
                    batch.drop_constraint("ck_escrow_deposit_positive_amount", type_="check")
                except Exception:
                    pass
                batch.alter_column("amount", type_=sa.Float(asdecimal=False))

        # escrow_agreements — indices + contraintes
        if _index_exists("escrow_agreements", "ix_escrow_deadline"):
            op.drop_index("ix_escrow_deadline", table_name="escrow_agreements")
        if _index_exists("escrow_agreements", "ix_escrow_status"):
            op.drop_index("ix_escrow_status", table_name="escrow_agreements")

        if _table_exists("escrow_agreements"):
            with op.batch_alter_table("escrow_agreements", schema=None, reflect_kwargs={"resolve_fks": False}) as batch:
                try:
                    batch.drop_constraint("ck_escrow_amount_total_non_negative", type_="check")
                except Exception:
                    pass
                batch.alter_column("amount_total", type_=sa.Float(asdecimal=False))

        # transactions
        if _table_exists("transactions"):
            with op.batch_alter_table("transactions", schema=None, reflect_kwargs={"resolve_fks": False}) as batch:
                batch.alter_column("amount", type_=sa.Float(asdecimal=False))

    finally:
        op.execute(text("PRAGMA foreign_keys=ON"))

