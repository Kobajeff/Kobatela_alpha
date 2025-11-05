"""Payment execution services (PSP stub)."""
"""Payment execution services (PSP stub)."""
import logging
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    EscrowAgreement,
    EscrowDeposit,
    EscrowEvent,
    EscrowStatus,
    Milestone,
    MilestoneStatus,
    Payment,
    PaymentStatus,
)
from app.services.idempotency import get_existing_by_key
from app.utils.errors import error_response
from app.utils.time import utcnow

logger = logging.getLogger(__name__)



def _sum_deposits(db: Session, escrow_id: int) -> float:
    from app.models.escrow import EscrowDeposit

    stmt = select(func.coalesce(func.sum(EscrowDeposit.amount), 0.0)).where(EscrowDeposit.escrow_id == escrow_id)
    return float(db.scalar(stmt) or 0.0)


def _sum_payments(db: Session, escrow_id: int) -> float:
    stmt = select(func.coalesce(func.sum(Payment.amount), 0.0)).where(Payment.escrow_id == escrow_id)
    return float(db.scalar(stmt) or 0.0)


def available_balance(db: Session, escrow_id: int) -> float:
    """Return the remaining balance available for payouts on the escrow."""

    return _sum_deposits(db, escrow_id) - _sum_payments(db, escrow_id)
  
def _escrow_available(db: Session, escrow_id: int) -> float:
    """Dépôts confirmés – paiements déjà envoyés."""
    deposited = float(
        db.scalar(
            select(func.coalesce(func.sum(EscrowDeposit.amount), 0.0))
            .where(EscrowDeposit.escrow_id == escrow_id)
        ) or 0.0
    )
    paid_out = float(
        db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0.0))
            .where(Payment.escrow_id == escrow_id, Payment.status == PaymentStatus.SENT)
        ) or 0.0
    )
    return deposited - paid_out


def execute_payout(
    db: Session,
    *,
    escrow: EscrowAgreement,
    milestone: Optional[Milestone],
    amount: float,
    idempotency_key: str,
) -> Payment:
    """
    Exécute un payout de manière idempotente :
      - réutilise Payment s’il existe via idempotency_key
      - vérifie le solde dispo du séquestre
      - marque Payment SENT (stub PSP), et le milestone PAID si fourni
      - journalise un EscrowEvent et un AuditLog
    """
    # Idempotence : réutilisation
    payment = get_existing_by_key(db, Payment, idempotency_key)
    if payment:
        logger.info("Reusing existing payment", extra={"payment_id": payment.id})
        if payment.status != PaymentStatus.SENT:
            payment.status = PaymentStatus.SENT
            payment.psp_ref = payment.psp_ref or f"PSP-{payment.id}"
            if milestone and milestone.status != MilestoneStatus.PAID:
                milestone.status = MilestoneStatus.PAID
            db.commit()
        return payment

    # Solde séquestre
    available = _escrow_available(db, escrow.id)
    if amount > available + 1e-9:
        raise ValueError(f"Insufficient escrow balance: need {amount}, available {available}")

    # Création + “envoi” PSP (stub)
    payment = Payment(
        escrow_id=escrow.id,
        milestone_id=(milestone.id if milestone else None),
        amount=amount,
        status=PaymentStatus.INITIATED,
        idempotency_key=idempotency_key,
    )
    db.add(payment)
    db.flush()

    payment.status = PaymentStatus.SENT
    payment.psp_ref = f"PSP-{payment.id}"

    if milestone and milestone.status != MilestoneStatus.PAID:
        milestone.status = MilestoneStatus.PAID

    # Events / audit
    db.add(
        EscrowEvent(
            escrow_id=escrow.id,
            kind="PAYMENT_SENT",
            data_json={
                "payment_id": payment.id,
                "amount": amount,
                "milestone_id": milestone.id if milestone else None,
                "psp_ref": payment.psp_ref,
            },
            at=utcnow(),
        )
    )
    db.add(
        AuditLog(
            actor="system",
            action="EXECUTE_PAYOUT",
            entity="Payment",
            entity_id=payment.id,
            data_json={"idempotency_key": idempotency_key, "amount": amount},
            at=utcnow(),
        )
    )

    _finalize_escrow_if_paid(db, escrow.id)

    db.commit()
    db.refresh(payment)
    if milestone:
        db.refresh(milestone)
    return payment


def execute_payment(db: Session, payment_id: int) -> Payment:
    """
    Shim de compatibilité : exécute un Payment existant en
    appelant execute_payout avec une idempotency_key stable.
    """
    payment = db.get(Payment, payment_id)
    if not payment:
        raise ValueError("Payment not found")

    escrow = db.get(EscrowAgreement, payment.escrow_id)
    milestone = db.get(Milestone, payment.milestone_id) if payment.milestone_id else None
    idem = payment.idempotency_key or f"payment:{payment.id}"

    executed = execute_payout(
        db,
        escrow=escrow,
        milestone=milestone,
        amount=payment.amount,
        idempotency_key=idem,
    )
    return executed


def _finalize_escrow_if_paid(db: Session, escrow_id: int) -> None:
    """Si tous les jalons sont payés → escrow RELEASED + event."""
    remaining = int(
        db.scalar(
            select(func.count()).select_from(Milestone).where(
                Milestone.escrow_id == escrow_id,
                Milestone.status != MilestoneStatus.PAID,
            )
        ) or 0
    )
    if remaining == 0:
        escrow = db.get(EscrowAgreement, escrow_id)
        if escrow and escrow.status != EscrowStatus.RELEASED:
            escrow.status = EscrowStatus.RELEASED
            db.add(
                EscrowEvent(
                    escrow_id=escrow_id,
                    kind="CLOSED",
                    data_json={"reason": "all_milestones_paid"},
                    at=utcnow(),
                )
            )


__all__ = ["execute_payout", "execute_payment"]
