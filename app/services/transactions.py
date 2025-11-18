"""Transaction service."""
import logging
from typing import Tuple

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.allowlist import AllowedRecipient
from app.models.audit import AuditLog
from app.models.certified import CertifiedAccount
from app.models.transaction import Transaction, TransactionStatus
from app.schemas.transaction import AllowlistCreate, CertificationCreate, TransactionCreate
from app.services import alerts as alert_service
from app.services.idempotency import get_existing_by_key
from app.utils.errors import error_response
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

ALERT_UNAUTHORIZED = "UNAUTHORIZED_TRANSFER_ATTEMPT"


def _audit(
    db: Session,
    *,
    actor: str,
    action: str,
    entity: str,
    entity_id: int | None,
    data: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            actor=actor,
            action=action,
            entity=entity,
            entity_id=entity_id,
            data_json=data or {},
            at=utcnow(),
        )
    )


def add_to_allowlist(
    db: Session, payload: AllowlistCreate, *, actor: str | None = None
) -> dict[str, str]:
    """Add a recipient to the sender allowlist and audit the mutation."""

    exists_stmt = select(AllowedRecipient).where(
        AllowedRecipient.owner_id == payload.owner_id,
        AllowedRecipient.recipient_id == payload.recipient_id,
    )
    if db.execute(exists_stmt).first():
        return {"status": "exists"}

    entry = AllowedRecipient(owner_id=payload.owner_id, recipient_id=payload.recipient_id)
    db.add(entry)
    db.flush()
    _audit(
        db,
        actor=actor or "admin",
        action="ALLOWLIST_ADD",
        entity="AllowedRecipient",
        entity_id=entry.id,
        data={
            "owner_id": payload.owner_id,
            "recipient_id": payload.recipient_id,
            "category_id": getattr(payload, "category_id", None),
        },
    )
    db.commit()
    logger.info(
        "Allowlist entry created",
        extra={"owner_id": payload.owner_id, "recipient_id": payload.recipient_id},
    )
    return {"status": "added"}


def add_certification(
    db: Session, payload: CertificationCreate, *, actor: str | None = None
) -> dict[str, str]:
    """Create or update a certified account entry with an audit trail."""

    stmt = select(CertifiedAccount).where(CertifiedAccount.user_id == payload.user_id)
    account = db.scalars(stmt).one_or_none()
    now = utcnow()
    if account:
        account.level = payload.level
        account.certified_at = now
        status_label = "updated"
        entity_id = account.id
    else:
        account = CertifiedAccount(user_id=payload.user_id, level=payload.level, certified_at=now)
        db.add(account)
        db.flush()
        status_label = "created"
        entity_id = account.id

    _audit(
        db,
        actor=actor or "admin",
        action="CERTIFICATION_UPDATE",
        entity="CertifiedAccount",
        entity_id=entity_id,
        data={"account_id": payload.user_id, "level": payload.level},
    )
    db.commit()
    logger.info("Account certification updated", extra={"user_id": payload.user_id, "level": payload.level})
    return {"status": status_label}


def create_transaction(
    db: Session,
    payload: TransactionCreate,
    *,
    idempotency_key: str | None,
    actor: str | None = None,
) -> Tuple[Transaction, bool]:
    """Create a restricted transaction, returning the entity and whether it was newly created."""

    if idempotency_key:
        existing = get_existing_by_key(db, Transaction, idempotency_key)
        if existing:
            logger.info("Idempotent transaction reused", extra={"transaction_id": existing.id})
            return existing, False

    allowed_stmt = select(AllowedRecipient).where(
        AllowedRecipient.owner_id == payload.sender_id,
        AllowedRecipient.recipient_id == payload.receiver_id,
    )
    certified_stmt = select(CertifiedAccount).where(CertifiedAccount.user_id == payload.receiver_id)

    allowed = db.execute(allowed_stmt).first() is not None
    certified = db.execute(certified_stmt).first() is not None

    if not allowed and not certified:
        alert_service.create_alert(
            db,
            alert_type=ALERT_UNAUTHORIZED,
            message="Receiver is not allowlisted or certified.",
            actor_user_id=payload.sender_id,
            payload={
                "sender_id": payload.sender_id,
                "attempted_receiver_id": payload.receiver_id,
                "amount": str(payload.amount),
            },
        )
        logger.warning("Unauthorized transfer attempt", extra=payload.model_dump())
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response("UNAUTHORIZED_TRANSFER", "Receiver is not allowlisted or certified."),
        )

    transaction = Transaction(
        sender_id=payload.sender_id,
        receiver_id=payload.receiver_id,
        amount=payload.amount,
        currency=payload.currency,
        status=TransactionStatus.COMPLETED,
        idempotency_key=idempotency_key,
    )
    try:
        db.add(transaction)
        db.flush()

        audit = AuditLog(
            actor=actor or "system",
            action="CREATE_TRANSACTION",
            entity="Transaction",
            entity_id=transaction.id,
            data_json=payload.model_dump(mode="json"),
            at=utcnow(),
        )
        db.add(audit)
        db.commit()
        db.refresh(transaction)

        logger.info("Transaction completed", extra={"transaction_id": transaction.id})
        return transaction, True
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            existing = get_existing_by_key(db, Transaction, idempotency_key)
            if existing:
                logger.info(
                    "Idempotent transaction reused after race",
                    extra={"transaction_id": existing.id},
                )
                return existing, False
        raise
