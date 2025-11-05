"""Conditional usage spending services."""
import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.allowed_payee import AllowedPayee
from app.models.audit import AuditLog
from app.models.escrow import EscrowAgreement, EscrowEvent, EscrowStatus
from app.models.payment import Payment
from app.services.idempotency import get_existing_by_key
from app.services.payments import available_balance, execute_payout
from app.utils.errors import error_response
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


def add_allowed_payee(
    db: Session,
    *,
    escrow_id: int,
    payee_ref: str,
    label: str,
    daily_limit: float | None = None,
    total_limit: float | None = None,
) -> AllowedPayee:
    """Register a payee that is allowed to receive conditional usage payouts."""

    today = utcnow().date()

    payee = AllowedPayee(
        escrow_id=escrow_id,
        payee_ref=payee_ref,
        label=label,
        daily_limit=daily_limit,
        total_limit=total_limit,
        last_reset_at=today,
    )
    db.add(payee)

    audit = AuditLog(
        actor="system",
        action="ADD_ALLOWED_PAYEE",
        entity="AllowedPayee",
        data_json={
            "escrow_id": escrow_id,
            "payee_ref": payee_ref,
            "limits": {"daily": daily_limit, "total": total_limit},
        },
        at=utcnow(),
    )
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        logger.info(
            "Allowed payee already exists", extra={"escrow_id": escrow_id, "payee_ref": payee_ref}
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("PAYEE_ALREADY_ALLOWED", "This payee is already allowed for this escrow."),
        ) from exc

    audit.entity_id = payee.id
    db.add(audit)
    db.commit()
    db.refresh(payee)
    logger.info("Allowed payee added", extra={"payee_id": payee.id, "escrow_id": escrow_id})
    return payee


def spend_to_allowed_payee(
    db: Session,
    *,
    escrow_id: int,
    payee_ref: str,
    amount: float,
    idempotency_key: str,
    note: str | None = None,
) -> Payment:
    """Execute a payout toward an allowed payee respecting configured limits."""

    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response("BAD_AMOUNT", "Amount must be greater than zero."),
        )

    existing_payment = get_existing_by_key(db, Payment, idempotency_key)
    if existing_payment:
        logger.info(
            "Usage spend idempotent reuse",
            extra={"payment_id": existing_payment.id, "escrow_id": escrow_id, "idem": idempotency_key},
        )
        return existing_payment

    escrow = db.get(EscrowAgreement, escrow_id)
    if escrow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("ESCROW_NOT_FOUND", "Escrow not found."),
        )

    if escrow.status in {EscrowStatus.RELEASED, EscrowStatus.REFUNDED, EscrowStatus.CANCELLED}:
        logger.warning(
            "Escrow closed for usage spend", extra={"escrow_id": escrow_id, "status": escrow.status.value}
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("ESCROW_NOT_ACTIVE", "Escrow is no longer available for spending."),
        )

    payee_stmt = select(AllowedPayee).where(
        AllowedPayee.escrow_id == escrow_id,
        AllowedPayee.payee_ref == payee_ref,
    )
    payee = db.scalars(payee_stmt).first()
    if payee is None:
        logger.warning(
            "Usage spend for unauthorized payee", extra={"escrow_id": escrow_id, "payee_ref": payee_ref}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response("PAYEE_NOT_ALLOWED", "This payee is not allowed for this escrow."),
        )

    today = utcnow().date()
    if payee.last_reset_at is None or payee.last_reset_at != today:
        logger.info(
            "Resetting daily spend counters",
            extra={"escrow_id": escrow_id, "payee_ref": payee_ref, "previous_date": payee.last_reset_at},
        )
        payee.spent_today = 0.0
        payee.last_reset_at = today

    if payee.daily_limit is not None and (payee.spent_today + amount) > payee.daily_limit + 1e-9:
        logger.info(
            "Daily limit reached",
            extra={"escrow_id": escrow_id, "payee_ref": payee_ref, "amount": amount},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("DAILY_LIMIT_REACHED", "Daily limit would be exceeded."),
        )

    if payee.total_limit is not None and (payee.spent_total + amount) > payee.total_limit + 1e-9:
        logger.info(
            "Total limit reached",
            extra={"escrow_id": escrow_id, "payee_ref": payee_ref, "amount": amount},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("TOTAL_LIMIT_REACHED", "Total limit would be exceeded."),
        )

    balance = available_balance(db, escrow_id=escrow.id)
    if amount > balance + 1e-9:
        logger.warning(
            "Insufficient escrow balance for usage spend",
            extra={"escrow_id": escrow_id, "amount": amount, "balance": balance},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("INSUFFICIENT_ESCROW_BALANCE", "Not enough escrow balance."),
        )

    try:
        payment = execute_payout(
            db,
            escrow=escrow,
            milestone=None,
            amount=amount,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("INSUFFICIENT_ESCROW_BALANCE", str(exc)),
        ) from exc

    event_exists_stmt = select(EscrowEvent).where(
        EscrowEvent.escrow_id == escrow.id,
        EscrowEvent.kind == "USAGE_SPEND",
        EscrowEvent.data_json["idempotency_key"].as_string() == idempotency_key,
    )
    if db.execute(event_exists_stmt).first():
        logger.info(
            "Usage spend event already recorded",
            extra={"payment_id": payment.id, "escrow_id": escrow.id, "idem": idempotency_key},
        )
        return payment

    payee.spent_today = float(payee.spent_today or 0.0) + amount
    payee.spent_total = float(payee.spent_total or 0.0) + amount
    payee.last_reset_at = today

    event = EscrowEvent(
        escrow_id=escrow.id,
        kind="USAGE_SPEND",
        data_json={
            "payment_id": payment.id,
            "amount": amount,
            "payee_ref": payee_ref,
            "note": note,
            "idempotency_key": idempotency_key,
        },
        at=utcnow(),
    )
    audit = AuditLog(
        actor="system",
        action="USAGE_SPEND",
        entity="Payment",
        entity_id=payment.id,
        data_json={"escrow_id": escrow.id, "payee_ref": payee_ref, "amount": amount},
        at=utcnow(),
    )
    db.add_all([payee, event, audit])
    db.commit()
    logger.info(
        "Usage spend executed",
        extra={"payment_id": payment.id, "escrow_id": escrow.id, "payee_ref": payee_ref, "amount": amount},
    )
    return payment


__all__ = ["add_allowed_payee", "spend_to_allowed_payee"]
