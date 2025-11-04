"""Payment execution services."""
import logging

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import EscrowAgreement, Milestone, MilestoneStatus, Payment, PaymentStatus
from app.services.idempotency import get_existing_by_key
from app.utils.errors import error_response
from sqlalchemy.orm import Session

from app.models import AuditLog, EscrowAgreement, EscrowStatus, Milestone, MilestoneStatus, Payment, PaymentStatus
from app.services import milestones as milestones_service
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
        if existing.status != PaymentStatus.SENT:
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
        status=PaymentStatus.INITIATED,
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
def execute_payment(db: Session, payment_id: int) -> Payment:
    """Execute a payment and update related state."""

    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("PAYMENT_NOT_FOUND", "Payment not found."),
        )

    if payment.status == PaymentStatus.SENT:
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
    milestone = db.get(Milestone, payment.milestone_id) if payment.milestone_id else None
    if milestone and milestone.status == MilestoneStatus.PAID:
        logger.info("Milestone already marked as paid", extra={"milestone_id": milestone.id})
        payment.status = PaymentStatus.SENT
        _finalize_escrow_if_paid(db, payment.escrow_id)
        db.commit()
        db.refresh(payment)
        return payment

    if milestone:
        milestone.status = MilestoneStatus.PAYING

    # Simulate successful PSP call.
    payment.status = PaymentStatus.SENT
    payment.psp_ref = payment.psp_ref or f"PSP-{payment.id}"
    if milestone:
        milestone.status = MilestoneStatus.PAID

    db.add(
        AuditLog(
            actor="system",
            action="EXECUTE_PAYMENT",
            entity="Payment",
            entity_id=payment.id,
            data_json={"payment_id": payment.id, "status": payment.status.value},
            at=utcnow(),
        )
    )

    _finalize_escrow_if_paid(db, payment.escrow_id)

    db.commit()
    db.refresh(payment)
    if milestone:
        db.refresh(milestone)
    logger.info(
        "Payment executed",
        extra={"payment_id": payment.id, "status": payment.status.value, "escrow_id": payment.escrow_id},
    )
    return payment


def _finalize_escrow_if_paid(db: Session, escrow_id: int) -> None:
    escrow = db.get(EscrowAgreement, escrow_id)
    if escrow is None:
        return

    db.flush()
    stmt = select(func.count()).select_from(Milestone).where(
        Milestone.escrow_id == escrow_id,
        Milestone.status != MilestoneStatus.PAID,
    )
    remaining = db.scalar(stmt) or 0
    if remaining == 0 or milestones_service.all_milestones_paid(db, escrow_id):
    if remaining == 0:
        escrow.status = EscrowStatus.RELEASED
        logger.info("Escrow released after payments", extra={"escrow_id": escrow.id})


__all__ = ["execute_payment"]
