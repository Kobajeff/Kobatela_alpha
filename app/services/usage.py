"""Conditional usage spending services."""
import logging
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.allowed_payee import AllowedPayee
from app.models.audit import AuditLog
from app.models.escrow import EscrowAgreement, EscrowEvent, EscrowStatus
from app.models.payment import Payment
from app.services.idempotency import get_existing_by_key
from app.services.payments import available_balance, execute_payout, finalize_payment_settlement
from app.utils.audit import log_audit
from app.utils.errors import error_response
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

EPS = Decimal("1e-9")


def _audit_usage(
    db: Session,
    *,
    action: str,
    escrow_id: int,
    payee_ref: str,
    amount: Decimal,
    entity_id: int | None = None,
    note: str | None = None,
    actor: str | None = None,
) -> None:
    payload = {
        "escrow_id": escrow_id,
        "payee_ref": payee_ref,
        "amount": str(amount),
    }
    if note is not None:
        payload["note"] = note
    log_audit(
        db,
        actor=actor or "system",
        action=action,
        entity="AllowedPayee",
        entity_id=entity_id,
        data=payload,
    )

def add_allowed_payee(
    db: Session,
    *,
    escrow_id: int,
    payee_ref: str,
    label: str,
    daily_limit: Decimal | None = None,
    total_limit: Decimal | None = None,
    actor: str | None = None,
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
        actor=actor or "system",
        action="ADD_ALLOWED_PAYEE",
        entity="AllowedPayee",
        data_json={
            "escrow_id": escrow_id,
            "payee_ref": payee_ref,
            "limits": {
                "daily": str(daily_limit) if daily_limit is not None else None,
                "total": str(total_limit) if total_limit is not None else None,
            },
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
    amount: Decimal,
    idempotency_key: str,
    note: str | None = None,
    actor: str | None = None,
) -> Payment:
    """Execute a payout toward an allowed payee respecting configured limits."""

    if amount <= Decimal("0"):
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
        _audit_usage(
            db,
            action="USAGE_ESCROW_NOT_FOUND",
            escrow_id=escrow_id,
            payee_ref=payee_ref,
            amount=amount,
            actor=actor,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("ESCROW_NOT_FOUND", "Escrow not found."),
        )

    if escrow.status in {EscrowStatus.RELEASED, EscrowStatus.REFUNDED, EscrowStatus.CANCELLED}:
        logger.warning(
            "Escrow closed for usage spend", extra={"escrow_id": escrow_id, "status": escrow.status.value}
        )
        _audit_usage(
            db,
            action="USAGE_ESCROW_CLOSED",
            escrow_id=escrow_id,
            payee_ref=payee_ref,
            amount=amount,
            note=escrow.status.value,
            actor=actor,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("ESCROW_NOT_ACTIVE", "Escrow is no longer available for spending."),
        )

    payee_stmt = (
        select(AllowedPayee)
        .where(
            AllowedPayee.escrow_id == escrow_id,
            AllowedPayee.payee_ref == payee_ref,
        )
        .with_for_update()
    )
    payee = db.execute(payee_stmt).scalar_one_or_none()
    if payee is None:
        logger.warning(
            "Usage spend for unauthorized payee", extra={"escrow_id": escrow_id, "payee_ref": payee_ref}
        )
        _audit_usage(
            db,
            action="USAGE_PAYEE_FORBIDDEN",
            escrow_id=escrow_id,
            payee_ref=payee_ref,
            amount=amount,
            actor=actor,
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
        payee.spent_today = Decimal("0")
        payee.last_reset_at = today

    spent_today = (payee.spent_today or Decimal("0"))
    spent_total = (payee.spent_total or Decimal("0"))

    new_daily = spent_today + amount
    new_total = spent_total + amount

    if payee.daily_limit is not None and new_daily > payee.daily_limit:
        logger.info(
            "Daily limit reached",
            extra={"escrow_id": escrow_id, "payee_ref": payee_ref, "amount": amount},
        )
        _audit_usage(
            db,
            action="USAGE_DAILY_LIMIT_REJECTED",
            escrow_id=escrow_id,
            payee_ref=payee_ref,
            amount=amount,
            entity_id=payee.id,
            actor=actor,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("DAILY_LIMIT_REACHED", "Daily limit would be exceeded."),
        )

    if payee.total_limit is not None and new_total > payee.total_limit + EPS:
        logger.info(
            "Total limit reached",
            extra={"escrow_id": escrow_id, "payee_ref": payee_ref, "amount": amount},
        )
        _audit_usage(
            db,
            action="USAGE_TOTAL_LIMIT_REJECTED",
            escrow_id=escrow_id,
            payee_ref=payee_ref,
            amount=amount,
            entity_id=payee.id,
            actor=actor,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("TOTAL_LIMIT_REACHED", "Total limit would be exceeded."),
        )

    balance = available_balance(db, escrow_id=escrow.id)
    if amount > balance + EPS:
        logger.warning(
            "Insufficient escrow balance for usage spend",
            extra={"escrow_id": escrow_id, "amount": amount, "balance": balance},
        )
        _audit_usage(
            db,
            action="USAGE_BALANCE_REJECTED",
            escrow_id=escrow_id,
            payee_ref=payee_ref,
            amount=amount,
            entity_id=payee.id,
            actor=actor,
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

    finalize_payment_settlement(
        db,
        payment,
        source="usage-spend",
        extra={"idempotency_key": payment.idempotency_key, "note": note},
    )
    db.refresh(payment)

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

    payee.spent_today = new_daily
    payee.spent_total = new_total
    payee.last_reset_at = today

    event = EscrowEvent(
        escrow_id=escrow.id,
        kind="USAGE_SPEND",
        idempotency_key=idempotency_key,
        data_json={
            "payment_id": payment.id,
            "amount": str(amount),
            "payee_ref": payee_ref,
            "note": note,
            "idempotency_key": idempotency_key,
        },
        at=utcnow(),
    )
    audit = AuditLog(
        actor=actor or "system",
        action="USAGE_SPEND",
        entity="Payment",
        entity_id=payment.id,
        data_json={
            "escrow_id": escrow.id,
            "payee_ref": payee_ref,
            "amount": str(amount),
        },
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
