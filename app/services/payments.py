"""Payment execution services."""
import logging
from decimal import Decimal
from uuid import uuid4
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
from app.utils.audit import sanitize_payload_for_audit
from app.utils.errors import error_response
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

def _to_decimal(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))

def _sum_deposits(db: Session, escrow_id: int) -> Decimal:

    stmt = select(func.coalesce(func.sum(EscrowDeposit.amount), 0)).where(EscrowDeposit.escrow_id == escrow_id)
    value = db.scalar(stmt)
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(value)


def _sum_payments(db: Session, escrow_id: int) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.escrow_id == escrow_id)
        .where(Payment.status.in_([PaymentStatus.SENT, PaymentStatus.SETTLED]))
    )
    value = db.scalar(stmt)
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(value)


def available_balance(db: Session, escrow_id: int) -> Decimal:
    """Return the remaining balance available for payouts on the escrow."""

    return _sum_deposits(db, escrow_id) - _sum_payments(db, escrow_id)

def _escrow_available(db: Session, escrow_id: int) -> Decimal:
    """Dépôts confirmés – paiements déjà envoyés (statuts débitants)."""
    # dépôts
    deposited = _sum_deposits(db, escrow_id)
    # paiements effectivement débités (SENT/SETTLED)
    stmt = (
        select(func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.escrow_id == escrow_id)
        .where(Payment.status.in_([PaymentStatus.SENT, PaymentStatus.SETTLED]))
    )
    paid_value = db.scalar(stmt)
    if paid_value is None:
        paid = Decimal("0")
    elif isinstance(paid_value, Decimal):
        paid = paid_value
    else:
        paid = Decimal(paid_value)
    return deposited - paid


def execute_payout(
    db: Session,
    *,
    escrow: EscrowAgreement,
    milestone: Optional[Milestone],
    amount: Decimal,
    idempotency_key: str,
) -> Payment:
    """Execute (or reuse) a payout in an idempotent fashion."""
    amount = _to_decimal(amount)
    # 1) Idempotence par clé
    existing = get_existing_by_key(db, Payment, idempotency_key)
    if existing:
        logger.info(
            "Reusing existing payment",
            extra={"payment_id": existing.id, "idem": idempotency_key},
        )
        if existing.psp_ref is None:
            existing.psp_ref = f"PSP-{uuid4()}"
            db.add(existing)
            db.flush()

        # États terminaux ou déjà envoyés => on renvoie tel quel
        if existing.status in (PaymentStatus.SENT, PaymentStatus.SETTLED):
            return existing

        # Ne jamais "promouvoir" une erreur silencieusement
        if existing.status == PaymentStatus.ERROR:
            raise ValueError("Existing payment is in ERROR. Use a new idempotency key to retry.")

        # PENDING -> on finalise l'envoi (stub PSP) et on met à jour le milestone
        if existing.status == PaymentStatus.PENDING:
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
        raise ValueError(f"Existing payment not in reusable state: {existing.status}")

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
            if not reuse_candidate.idempotency_key:
                reuse_candidate.idempotency_key = idempotency_key
                db.add(reuse_candidate)
                db.commit()
            return reuse_candidate

    # 3) Solde séquestre suffisant ?
    if available_balance(db, escrow.id) < amount:
        logger.warning(
            "Insufficient escrow balance for payout",
            extra={"escrow_id": escrow.id, "amount": str(amount)},
        )
        raise ValueError("INSUFFICIENT_ESCROW_BALANCE")

    # 4) Création + “envoi” PSP (stub)
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
            extra={"escrow_id": escrow.id, "amount": str(amount), "milestone_id": getattr(milestone, "id", None)},
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
        _handle_post_payment(db, payment)
        db.add(
            AuditLog(
                actor="system",
                action="PAYMENT_EXECUTED",
                entity="Payment",
                entity_id=payment.id,
                data_json=sanitize_payload_for_audit(
                    {
                        "escrow_id": payment.escrow_id,
                        "milestone_id": payment.milestone_id,
                        "amount": str(payment.amount),
                        "idempotency_key": payment.idempotency_key,
                        "psp_ref": payment.psp_ref,
                    }
                ),
                at=utcnow(),
            )
        )
        db.commit()
        logger.info(
            "Payout executed",
            extra={"payment_id": payment.id, "escrow_id": escrow.id, "status": payment.status.value},
        )
        return payment

    except IntegrityError:
        # Course condition idempotence: on récupère par clé
        db.rollback()
        existing = get_existing_by_key(db, Payment, idempotency_key)
        if existing:
            logger.info(
                "Payout idempotent reuse after race",
                extra={"payment_id": existing.id, "idem": idempotency_key},
            )
            return existing
        raise

def _handle_post_payment(db: Session, payment: Payment) -> None:
    """Synchronise escrow state once a payment has been persisted.

    This keeps the escrow lifecycle consistent after any payout:
    - if the escrow is now fully paid, it will be closed by `_finalize_escrow_if_paid`.
    """

    if payment is None or payment.escrow_id is None:
        return

    _finalize_escrow_if_paid(db, payment.escrow_id)

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
                    "amount": str(payment.amount),
                    "milestone_id": milestone.id if milestone else None,
                    "psp_ref": payment.psp_ref,
                },
                at=utcnow(),
            )
        )
        db.add(
            AuditLog(
                actor="system",
                action="PAYMENT_EXECUTED",
                entity="Payment",
                entity_id=payment.id,
                data_json=sanitize_payload_for_audit(
                    {
                        "idempotency_key": payment.idempotency_key,
                        "amount": str(payment.amount),
                        "escrow_id": payment.escrow_id,
                        "milestone_id": payment.milestone_id,
                    }
                ),
                at=utcnow(),
            )
        )
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
    finalize_payment_settlement(
        db,
        payment,
        source="manual-execute",
        extra={"idempotency_key": payment.idempotency_key},
    )
    db.refresh(payment)
    db.refresh(executed)
    return executed

def finalize_payment_settlement(
    db: Session,
    payment: Payment,
    *,
    source: str,
    extra: dict | None = None,
) -> None:
    """Mark a payment as settled and propagate escrow closure when appropriate."""

    if payment is None or payment.escrow_id is None:
        return

    if payment.status == PaymentStatus.SETTLED:
        return

    now = utcnow()
    payment.status = PaymentStatus.SETTLED
    db.add(payment)

    event_key = f"payment:{payment.id}:settled"
    existing_event = db.scalar(
        select(EscrowEvent.id).where(
            EscrowEvent.escrow_id == payment.escrow_id,
            EscrowEvent.idempotency_key == event_key,
        )
    )
    payload = {
        "payment_id": payment.id,
        "amount": str(payment.amount),
        "source": source,
    }
    if extra:
        payload.update(extra)

    if existing_event is None:
        db.add(
            EscrowEvent(
                escrow_id=payment.escrow_id,
                kind="PAYMENT_SETTLED",
                idempotency_key=event_key,
                data_json=payload,
                at=now,
            )
        )

    db.add(
        AuditLog(
            actor=source,
            action="PAYMENT_SETTLED",
            entity="Payment",
            entity_id=payment.id,
            data_json=sanitize_payload_for_audit(
                {
                    "escrow_id": payment.escrow_id,
                    "amount": str(payment.amount),
                    "source": source,
                    **(extra or {}),
                }
            ),
            at=now,
        )
    )

    _finalize_escrow_if_paid(db, payment.escrow_id)
    db.commit()


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
            now = utcnow()
            escrow.status = EscrowStatus.RELEASED
            db.add(
                EscrowEvent(
                    escrow_id=escrow_id,
                    kind="CLOSED",
                    data_json={"reason": "all_milestones_paid"},
                    at=now,
                )
            )
            db.add(
                AuditLog(
                    actor="system",
                    action="ESCROW_RELEASED",
                    entity="EscrowAgreement",
                    entity_id=escrow_id,
                    data_json=sanitize_payload_for_audit({"source": "_finalize_escrow_if_paid"}),
                    at=now,
                )
            )
            db.commit()

__all__ = ["available_balance", "execute_payment", "execute_payout", "finalize_payment_settlement"]
