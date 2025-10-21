"""Escrow service logic."""
import logging

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.escrow import EscrowAgreement, EscrowDeposit, EscrowEvent, EscrowStatus
from app.schemas.escrow import EscrowCreate, EscrowDepositCreate, EscrowActionPayload
from app.services.idempotency import get_existing_by_key
from app.utils.errors import error_response
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


def create_escrow(db: Session, payload: EscrowCreate) -> EscrowAgreement:
    """Create a new escrow agreement."""

    agreement = EscrowAgreement(
        client_id=payload.client_id,
        provider_id=payload.provider_id,
        amount_total=payload.amount_total,
        currency=payload.currency,
        release_conditions_json=payload.release_conditions,
        deadline_at=payload.deadline_at,
        status=EscrowStatus.DRAFT,
    )
    db.add(agreement)
    db.commit()
    db.refresh(agreement)
    logger.info("Escrow created", extra={"escrow_id": agreement.id})
    return agreement


def _total_deposited(db: Session, escrow_id: int) -> float:
    stmt = select(func.coalesce(func.sum(EscrowDeposit.amount), 0.0)).where(EscrowDeposit.escrow_id == escrow_id)
    return float(db.scalar(stmt) or 0.0)


def deposit(db: Session, escrow_id: int, payload: EscrowDepositCreate, *, idempotency_key: str | None) -> EscrowAgreement:
    """Deposit funds into an escrow agreement."""

    agreement = db.get(EscrowAgreement, escrow_id)
    if not agreement:
        raise HTTPException(status_code=404, detail=error_response("ESCROW_NOT_FOUND", "Escrow not found."))

    if idempotency_key:
        existing = get_existing_by_key(db, EscrowDeposit, idempotency_key)
        if existing:
            logger.info("Idempotent escrow deposit reused", extra={"escrow_id": escrow_id, "deposit_id": existing.id})
            db.refresh(agreement)
            return agreement

    deposit = EscrowDeposit(escrow_id=agreement.id, amount=payload.amount, idempotency_key=idempotency_key)
    db.add(deposit)

    total = _total_deposited(db, agreement.id) + payload.amount
    if total >= agreement.amount_total:
        agreement.status = EscrowStatus.FUNDED

    event = EscrowEvent(
        escrow_id=agreement.id,
        kind="DEPOSIT",
        data_json={"amount": payload.amount},
        at=utcnow(),
    )
    db.add(event)
    db.commit()
    db.refresh(agreement)
    logger.info("Escrow deposit processed", extra={"escrow_id": agreement.id, "status": agreement.status})
    return agreement


def mark_delivered(db: Session, escrow_id: int, payload: EscrowActionPayload) -> EscrowAgreement:
    agreement = _get_escrow_or_404(db, escrow_id)

    agreement.status = EscrowStatus.RELEASABLE
    event = EscrowEvent(
        escrow_id=agreement.id,
        kind="PROOF_UPLOADED",
        data_json={"note": payload.note, "proof_url": payload.proof_url},
        at=utcnow(),
    )
    db.add(event)
    db.commit()
    db.refresh(agreement)
    logger.info("Escrow marked delivered", extra={"escrow_id": agreement.id})
    return agreement


def client_approve(db: Session, escrow_id: int, payload: EscrowActionPayload | None = None) -> EscrowAgreement:
    agreement = _get_escrow_or_404(db, escrow_id)

    agreement.status = EscrowStatus.RELEASED
    event = EscrowEvent(
        escrow_id=agreement.id,
        kind="CLIENT_APPROVED",
        data_json={"note": payload.note if payload else None},
        at=utcnow(),
    )
    db.add(event)
    db.commit()
    db.refresh(agreement)
    logger.info("Escrow approved", extra={"escrow_id": agreement.id})
    return agreement


def client_reject(db: Session, escrow_id: int, payload: EscrowActionPayload | None = None) -> EscrowAgreement:
    agreement = _get_escrow_or_404(db, escrow_id)

    event = EscrowEvent(
        escrow_id=agreement.id,
        kind="CLIENT_REJECTED",
        data_json={"note": payload.note if payload else None},
        at=utcnow(),
    )
    db.add(event)
    db.commit()
    db.refresh(agreement)
    logger.info("Escrow rejected", extra={"escrow_id": agreement.id})
    return agreement


def check_deadline(db: Session, escrow_id: int) -> EscrowAgreement:
    agreement = _get_escrow_or_404(db, escrow_id)

    if agreement.status == EscrowStatus.FUNDED and agreement.deadline_at <= utcnow():
        logger.info("Escrow deadline reached, auto-approving", extra={"escrow_id": agreement.id})
        return client_approve(db, escrow_id, None)
    return agreement


def _get_escrow_or_404(db: Session, escrow_id: int) -> EscrowAgreement:
    agreement = db.get(EscrowAgreement, escrow_id)
    if not agreement:
        raise HTTPException(status_code=404, detail=error_response("ESCROW_NOT_FOUND", "Escrow not found."))
    return agreement
