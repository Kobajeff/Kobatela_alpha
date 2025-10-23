"""Transaction and authorization endpoints."""
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.allowlist import AllowedRecipient
from app.models.certified import CertifiedAccount
from app.models.transaction import Transaction
from app.schemas.transaction import (
    AllowlistCreate,
    CertificationCreate,
    TransactionCreate,
    TransactionRead,
)
from app.security import require_api_key
from app.services.transactions import create_transaction
from app.utils.errors import error_response

router = APIRouter(tags=["transactions"], dependencies=[Depends(require_api_key)])
logger = logging.getLogger(__name__)


@router.post("/allowlist", status_code=status.HTTP_201_CREATED)
def add_to_allowlist(payload: AllowlistCreate, db: Session = Depends(get_db)) -> dict[str, str]:
    """Add a recipient to the sender's allowlist."""

    exists_stmt = select(AllowedRecipient).where(
        AllowedRecipient.owner_id == payload.owner_id, AllowedRecipient.recipient_id == payload.recipient_id
    )
    if db.execute(exists_stmt).first():
        return {"status": "exists"}

    entry = AllowedRecipient(owner_id=payload.owner_id, recipient_id=payload.recipient_id)
    db.add(entry)
    db.commit()
    logger.info(
        "Allowlist entry created", extra={"owner_id": payload.owner_id, "recipient_id": payload.recipient_id}
    )
    return {"status": "added"}


@router.post("/certified", status_code=status.HTTP_201_CREATED)
def add_certification(payload: CertificationCreate, db: Session = Depends(get_db)) -> dict[str, str]:
    """Mark a user as certified."""

    stmt = select(CertifiedAccount).where(CertifiedAccount.user_id == payload.user_id)
    account = db.scalars(stmt).one_or_none()
    now = datetime.now(tz=UTC)
    if account:
        account.level = payload.level
        account.certified_at = now
        status_label = "updated"
    else:
        account = CertifiedAccount(user_id=payload.user_id, level=payload.level, certified_at=now)
        db.add(account)
        status_label = "created"
    db.commit()
    logger.info("Certification %s", status_label, extra={"user_id": payload.user_id, "level": payload.level})
    return {"status": status_label}


@router.post("/transactions", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def post_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Transaction:
    """Create a restricted transaction."""

    transaction, _created = create_transaction(db, payload, idempotency_key=idempotency_key)
    return transaction


@router.get("/transactions/{transaction_id}", response_model=TransactionRead)
def get_transaction(transaction_id: int, db: Session = Depends(get_db)) -> Transaction:
    """Retrieve transaction details."""

    transaction = db.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("TRANSACTION_NOT_FOUND", "Transaction not found."),
        )
    return transaction
