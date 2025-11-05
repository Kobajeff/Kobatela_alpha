"""Payment execution services."""
import logging
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import EscrowAgreement, Milestone, MilestoneStatus, Payment, PaymentStatus
from app.services.idempotency import get_existing_by_key
from app.utils.errors import error_response

logger = logging.getLogger(__name__)


def _sum_deposits(db: Session, escrow_id: int) -> float:
    from app.models.escrow import EscrowDeposit

    stmt = select(func.coalesce(func.sum(EscrowDeposit.amount), 0.0)).where(EscrowDeposit.escrow_id == escrow_id)
    return float(db.scalar(stmt) or 0.0)


def _sum_payments(db: Session, escrow_id: int) -> float:
    stmt = (
        select(func.coalesce(func.sum(Payment.amount), 0.0))
        .where(Payment.escrow_id == escrow_id)
        .where(Payment.status.in_([PaymentStatus.SENT, PaymentStatus.SETTLED]))
    )
    return float(db.scalar(stmt) or 0.0)


def available_balance(db: Session, escrow_id: int) -> float:
    """Return the remaining balance available for payouts on the escrow."""

    return _sum_deposits(db, escrow_id) - _sum_payments(db, escrow_id)


def execute_payout(
    db: Session,
    *,
    escrow: EscrowAgreement,
    milestone: Milestone | None,
    amount: float,
    idempotency_key: str,
) -> Payment:
    """Execute (or reuse) a payout in an idempotent fashion."""

    existing = get_existing_by_key(db, Payment, idempotency_key)
    if existing:
        logger.info(
            "Payout idempotent reuse",
            extra={"payment_id": existing.id, "idem": idempotency_key},
        )
        if existing.psp_ref is None:
            existing.psp_ref = f"PSP-{uuid4()}"
        if existing.status in (PaymentStatus.SENT, PaymentStatus.SETTLED):
            return existing

        if milestone and milestone.status not in (MilestoneStatus.PAID, MilestoneStatus.PAYING):
            milestone.status = MilestoneStatus.PAYING

        existing.status = PaymentStatus.SENT

        if milestone:
            milestone.status = MilestoneStatus.PAID

        db.commit()
        db.refresh(existing)
        if milestone:
            db.refresh(milestone)
        return existing

    if milestone is not None:
        reuse_stmt = (
            select(Payment)
            .where(Payment.milestone_id == milestone.id, Payment.amount == amount)
            .order_by(Payment.created_at.desc())
        )
        reuse_candidate = db.scalars(reuse_stmt).first()
        if reuse_candidate and reuse_candidate.status in (PaymentStatus.SENT, PaymentStatus.SETTLED):
            logger.info(
                "Payout reuse matched existing milestone payment",
                extra={"payment_id": reuse_candidate.id, "milestone_id": milestone.id},
            )
            return reuse_candidate

    if available_balance(db, escrow.id) < amount:
        logger.warning(
            "Insufficient escrow balance for payout",
            extra={"escrow_id": escrow.id, "amount": amount},
        )
        raise ValueError("INSUFFICIENT_ESCROW_BALANCE")

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

        payment.psp_ref = payment.psp_ref or f"PSP-{uuid4()}"
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


__all__ = ["available_balance", "execute_payment", "execute_payout"]
