from __future__ import annotations

"""Transaction and authorization endpoints."""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.api_key import ApiScope
from app.models.transaction import Transaction
from app.schemas.transaction import (
    AllowlistCreate,
    CertificationCreate,
    TransactionCreate,
    TransactionRead,
)
from app.security import require_scope
from app.services import transactions as transactions_service
from app.utils.errors import error_response

# RBAC global : toutes les routes de ce router = admin ONLY
router = APIRouter(
    prefix="",
    tags=["transactions"],
    dependencies=[Depends(require_scope({ApiScope.admin}))],
)


@router.post(
    "/allowlist",
    status_code=status.HTTP_201_CREATED,
)
def add_to_allowlist(
    payload: AllowlistCreate,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Add a recipient to the sender's allowlist (admin only)."""

    return transactions_service.add_to_allowlist(db, payload)


@router.post(
    "/certified",
    status_code=status.HTTP_201_CREATED,
)
def add_certification(
    payload: CertificationCreate,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Mark a user as certified (admin only)."""

    return transactions_service.add_certification(db, payload)


@router.post(
    "/transactions",
    response_model=TransactionRead,
    status_code=status.HTTP_201_CREATED,
)
def post_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Transaction:
    """Create a restricted transaction (admin only)."""

    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(
                "IDEMPOTENCY_KEY_REQUIRED",
                "Header 'Idempotency-Key' is required for POST /transactions.",
            ),
        )

    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(
                "IDEMPOTENCY_KEY_REQUIRED",
                "Header 'Idempotency-Key' is required for POST /transactions.",
            ),
        )

    transaction, _created = transactions_service.create_transaction(
        db, payload, idempotency_key=idempotency_key
    )
    return transaction


@router.get(
    "/transactions/{transaction_id}",
    response_model=TransactionRead,
)
def get_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
) -> Transaction:
    """Retrieve transaction details (admin only)."""

    transaction = db.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("TRANSACTION_NOT_FOUND", "Transaction not found."),
        )
    return transaction
