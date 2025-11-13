"""Transaction and authorization endpoints."""
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.transaction import Transaction
from app.schemas.transaction import (
    AllowlistCreate,
    CertificationCreate,
    TransactionCreate,
    TransactionRead,
)
from app.security import require_api_key
from app.services import transactions as transactions_service
from app.utils.errors import error_response

router = APIRouter(tags=["transactions"], dependencies=[Depends(require_api_key)])


@router.post("/allowlist", status_code=status.HTTP_201_CREATED)
def add_to_allowlist(payload: AllowlistCreate, db: Session = Depends(get_db)) -> dict[str, str]:
    """Add a recipient to the sender's allowlist."""

    return transactions_service.add_to_allowlist(db, payload)


@router.post("/certified", status_code=status.HTTP_201_CREATED)
def add_certification(payload: CertificationCreate, db: Session = Depends(get_db)) -> dict[str, str]:
    """Mark a user as certified."""

    return transactions_service.add_certification(db, payload)


@router.post("/transactions", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def post_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Transaction:
    """Create a restricted transaction."""

    transaction, _created = transactions_service.create_transaction(db, payload, idempotency_key=idempotency_key)
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
