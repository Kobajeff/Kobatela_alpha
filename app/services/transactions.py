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
from app.schemas.transaction import TransactionCreate
from app.services import alerts as alert_service
from app.services.idempotency import get_existing_by_key
from app.utils.errors import error_response
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

ALERT_UNAUTHORIZED = "UNAUTHORIZED_TRANSFER_ATTEMPT"


def create_transaction(db: Session, payload: TransactionCreate, *, idempotency_key: str | None) -> Tuple[Transaction, bool]:
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
            actor="system",
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
