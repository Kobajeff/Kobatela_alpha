"""Escrow domain services."""
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.escrow import EscrowAgreement, EscrowDeposit, EscrowEvent, EscrowStatus
from app.schemas.escrow import EscrowCreate, EscrowDepositCreate, EscrowActionPayload
from app.services.idempotency import get_existing_by_key
from app.utils.errors import error_response
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


def _to_decimal(value: Any) -> Decimal:
    """
    Convertit proprement un montant en Decimal(2 décimales).
    Accepte Decimal, int, float, str. Lève ValueError si invalide.
    """
    if isinstance(value, Decimal):
        d = value
    else:
        try:
            # str() évite les artefacts binaires des floats
            d = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as e:
            raise ValueError(f"Invalid money amount: {value!r}") from e

    # Normalise à 2 décimales (montants en devise)
    return d.quantize(Decimal("0.01"))


def _audit(
    db: Session,
    *,
    actor: str,
    action: str,
    escrow: EscrowAgreement,
    data: dict[str, Any],
) -> None:
    """Persist an audit trail entry for escrow state changes."""

    db.add(
        AuditLog(
            actor=actor,
            action=action,
            entity="EscrowAgreement",
            entity_id=escrow.id,
            data_json=data,
            at=utcnow(),
        )
    )

def create_escrow(
    db: Session, payload: EscrowCreate, *, actor: str | None = None
) -> EscrowAgreement:
    """Create a new escrow agreement."""

    agreement = EscrowAgreement(
        client_id=payload.client_id,
        provider_id=payload.provider_id,
        amount_total=_to_decimal(payload.amount_total),   # <-- cast ici
        currency=payload.currency,
        release_conditions_json=payload.release_conditions,
        deadline_at=payload.deadline_at,
        status=EscrowStatus.DRAFT,
    )
    db.add(agreement)
    db.flush()
    _audit(
        db,
        actor=actor or "client",
        action="ESCROW_CREATED",
        escrow=agreement,
        data={
            "status": agreement.status.value,
            "amount_total": str(agreement.amount_total),
            "currency": agreement.currency,
        },
    )
    db.commit()
    db.refresh(agreement)
    logger.info("Escrow created", extra={"escrow_id": agreement.id})
    return agreement


def _total_deposited(db: Session, escrow_id: int) -> Decimal:
    stmt = select(func.coalesce(func.sum(EscrowDeposit.amount), 0)).where(EscrowDeposit.escrow_id == escrow_id)
    value = db.scalar(stmt)
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(value)


def deposit(
    db: Session,
    escrow_id: int,
    payload: EscrowDepositCreate,
    *,
    idempotency_key: str | None,
    actor: str | None = None,
) -> EscrowAgreement:
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

    # --- CAST ICI ---
    amount_dec = _to_decimal(payload.amount)

    deposit = EscrowDeposit(escrow_id=agreement.id, amount=amount_dec, idempotency_key=idempotency_key)
    try:
        db.add(deposit)

        # --- TOUT EN DECIMAL ---
        total = _total_deposited(db, agreement.id) + amount_dec
        # (agreement.amount_total est Decimal si défini en Numeric(asdecimal=True); au cas où:)
        amount_total_dec = _to_decimal(agreement.amount_total)
        if total >= amount_total_dec:
            agreement.status = EscrowStatus.FUNDED

        event_payload = {"amount": str(amount_dec)}
        if idempotency_key:
            event_payload["idempotency_key"] = idempotency_key
        event = EscrowEvent(
            escrow_id=agreement.id,
            kind="DEPOSIT",
            data_json=event_payload,
            at=utcnow(),
        )
        db.add(event)
        _audit(
            db,
            actor=actor or "system",
            action="ESCROW_DEPOSITED",
            escrow=agreement,
            data={
                "amount": str(amount_dec),
                "status": agreement.status.value,
                "idempotency_key": idempotency_key,
            },
        )
        db.commit()
        db.refresh(agreement)
        logger.info("Escrow deposit processed", extra={"escrow_id": agreement.id, "status": agreement.status})
        return agreement
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            existing = get_existing_by_key(db, EscrowDeposit, idempotency_key)
            if existing:
                logger.info(
                    "Idempotent escrow deposit reused after race",
                    extra={"escrow_id": escrow_id, "deposit_id": existing.id},
                )
                db.refresh(agreement)
                return agreement
        raise


def mark_delivered(
    db: Session, escrow_id: int, payload: EscrowActionPayload, *, actor: str | None = None
) -> EscrowAgreement:
    agreement = _get_escrow_or_404(db, escrow_id)

    agreement.status = EscrowStatus.RELEASABLE
    event = EscrowEvent(
        escrow_id=agreement.id,
        kind="PROOF_UPLOADED",
        data_json={"note": payload.note, "proof_url": payload.proof_url},
        at=utcnow(),
    )
    db.add(event)
    _audit(
        db,
        actor=actor or "provider",
        action="ESCROW_PROOF_UPLOADED",
        escrow=agreement,
        data={"status": agreement.status.value, "proof_url": payload.proof_url},
    )
    db.commit()
    db.refresh(agreement)
    logger.info("Escrow marked delivered", extra={"escrow_id": agreement.id})
    return agreement


def client_approve(
    db: Session,
    escrow_id: int,
    payload: EscrowActionPayload | None = None,
    *,
    actor: str | None = None,
) -> EscrowAgreement:
    agreement = _get_escrow_or_404(db, escrow_id)

    agreement.status = EscrowStatus.RELEASED
    event = EscrowEvent(
        escrow_id=agreement.id,
        kind="CLIENT_APPROVED",
        data_json={"note": payload.note if payload else None},
        at=utcnow(),
    )
    db.add(event)
    _audit(
        db,
        actor=actor or "client",
        action="ESCROW_RELEASED",
        escrow=agreement,
        data={"status": agreement.status.value, "note": payload.note if payload else None},
    )
    db.commit()
    db.refresh(agreement)
    logger.info("Escrow approved", extra={"escrow_id": agreement.id})
    return agreement


def client_reject(
    db: Session,
    escrow_id: int,
    payload: EscrowActionPayload | None = None,
    *,
    actor: str | None = None,
) -> EscrowAgreement:
    agreement = _get_escrow_or_404(db, escrow_id)

    # Idempotence : si déjà terminal, on renvoie tel quel
    if agreement.status in (EscrowStatus.RELEASED, EscrowStatus.REFUNDED, EscrowStatus.CANCELLED):
        return agreement

    # Choix du statut terminal :
    # - si des fonds ont été versés / livrés → remboursement
    # - sinon → annulation simple
    if agreement.status in (EscrowStatus.FUNDED, EscrowStatus.RELEASABLE):
        agreement.status = EscrowStatus.REFUNDED
    else:
        agreement.status = EscrowStatus.CANCELLED

    event = EscrowEvent(
        escrow_id=agreement.id,
        kind="CLIENT_REJECTED",
        data_json={"note": (payload.note if payload else None)},
        at=utcnow(),
    )
    db.add(event)
    _audit(
        db,
        actor=actor or "client",
        action="ESCROW_REJECTED" if agreement.status != EscrowStatus.CANCELLED else "ESCROW_CANCELLED",
        escrow=agreement,
        data={
            "status": agreement.status.value,
            "note": payload.note if payload else None,
        },
    )
    db.commit()
    db.refresh(agreement)
    logger.info("Escrow rejected", extra={"escrow_id": agreement.id, "status": agreement.status})
    return agreement


def check_deadline(
    db: Session, escrow_id: int, *, actor: str | None = None
) -> EscrowAgreement:
    agreement = _get_escrow_or_404(db, escrow_id)

    if agreement.status == EscrowStatus.FUNDED and agreement.deadline_at <= utcnow():
        logger.info("Escrow deadline reached, auto-approving", extra={"escrow_id": agreement.id})
        return client_approve(db, escrow_id, None, actor=actor or "system:deadline")
    return agreement


def _get_escrow_or_404(db: Session, escrow_id: int) -> EscrowAgreement:
    agreement = db.get(EscrowAgreement, escrow_id)
    if not agreement:
        raise HTTPException(status_code=404, detail=error_response("ESCROW_NOT_FOUND", "Escrow not found."))
    return agreement
