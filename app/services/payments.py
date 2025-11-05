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
        status=PaymentStatus.PENDING,
        idempotency_key=idempotency_key,
    )
    try:
        db.add(payment)
        logger.info(
            "Payout initiated",
            extra={"escrow_id": escrow.id, "amount": amount, "milestone_id": getattr(milestone, "id", None)},
        )
        if milestone:
            if milestone.status not in (MilestoneStatus.APPROVED, MilestoneStatus.PAYING):
                logger.info(
                    "Updating milestone status prior to payout",
                    extra={"milestone_id": milestone.id, "previous_status": milestone.status.value},
                )
            milestone.status = MilestoneStatus.PAYING

        payment.status = PaymentStatus.SENT
        if milestone:
            milestone.status = MilestoneStatus.PAID

        db.commit()
        db.refresh(payment)
        if milestone:
            db.refresh(milestone)
        logger.info(
            "Payout executed",
            extra={"payment_id": payment.id, "escrow_id": escrow.id, "status": payment.status.value},
        )
        return payment
    except IntegrityError:
        db.rollback()
        existing = get_existing_by_key(db, Payment, idempotency_key)
        if existing:
            logger.info(
                "Payout idempotent reuse after race",
                extra={"payment_id": existing.id, "idem": idempotency_key},
            )
            return existing
        raise


def execute_payment(db: Session, payment_id: int) -> Payment:
    """Execute a payment entity via the public endpoint."""

    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("PAYMENT_NOT_FOUND", "Payment not found."),
        )

    if payment.status in (PaymentStatus.SENT, PaymentStatus.SETTLED):
        logger.info("Payment already sent", extra={"payment_id": payment.id})
        return payment
    if payment.status == PaymentStatus.ERROR:
        logger.info("Payment previously failed", extra={"payment_id": payment.id})
        return payment

    escrow = db.get(EscrowAgreement, payment.escrow_id)
    if escrow is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("ESCROW_NOT_FOUND", "Escrow not found for payment."),
        )

    milestone = db.get(Milestone, payment.milestone_id) if payment.milestone_id else None
    if payment.idempotency_key is None:
        payment.idempotency_key = f"payment:{payment.id}"
        db.add(payment)
        db.flush()
        # après db.flush() sur payment
        payment.psp_ref = payment.psp_ref or f"PSP-{payment.id}"

        db.add(
            EscrowEvent(
                escrow_id=escrow.id,
                kind="PAYMENT_SENT",
                data_json={
                    "payment_id": payment.id,
                    "amount": payment.amount,
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
                data_json={"idempotency_key": payment.idempotency_key, "amount": payment.amount},,
                at=utcnow(),
            )
        )
        _finalize_escrow_if_paid(db, escrow.id)  # ← ajoute la fonction ci-dessous si pas encore là


    try:
        executed = execute_payout(
            db,
            escrow=escrow,
            milestone=milestone,
            amount=payment.amount,
            idempotency_key=payment.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("INSUFFICIENT_ESCROW_BALANCE", str(exc)),
        ) from exc

    db.refresh(payment)
    return executed

def _finalize_escrow_if_paid(db: Session, escrow_id: int) -> None:
    total = int(db.scalar(
        select(func.count()).select_from(Milestone).where(Milestone.escrow_id == escrow_id)
    ) or 0)
    if total == 0:
        return  # ne ferme pas les escrows sans jalons

    remaining = int(db.scalar(
        select(func.count()).select_from(Milestone).where(
            Milestone.escrow_id == escrow_id,
            Milestone.status != MilestoneStatus.PAID,
        )
    ) or 0)

    if remaining == 0:
        escrow = db.get(EscrowAgreement, escrow_id)
        if escrow and escrow.status != EscrowStatus.RELEASED:
            escrow.status = EscrowStatus.RELEASED
            db.add(EscrowEvent(
                escrow_id=escrow_id, kind="CLOSED",
                data_json={"reason": "all_milestones_paid"}, at=utcnow(),
            ))

__all__ = ["available_balance", "execute_payment", "execute_payout"]
