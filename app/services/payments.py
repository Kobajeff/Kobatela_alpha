"""Payment execution services."""
import logging

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, EscrowAgreement, EscrowStatus, Milestone, MilestoneStatus, Payment, PaymentStatus
from app.services import milestones as milestones_service
from app.utils.errors import error_response
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


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
