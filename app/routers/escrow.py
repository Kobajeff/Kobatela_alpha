"""Escrow endpoints."""
from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.escrow import EscrowAgreement
from app.schemas.escrow import EscrowActionPayload, EscrowCreate, EscrowDepositCreate, EscrowRead
from app.security import require_api_key
from app.services import escrow as escrow_service
from app.utils.errors import error_response

router = APIRouter(prefix="/escrows", tags=["escrow"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=EscrowRead, status_code=status.HTTP_201_CREATED)
def create_escrow(payload: EscrowCreate, db: Session = Depends(get_db)) -> EscrowAgreement:
    return escrow_service.create_escrow(db, payload)


@router.post("/{escrow_id}/deposit", response_model=EscrowRead, status_code=status.HTTP_200_OK)
def deposit(
    escrow_id: int,
    payload: EscrowDepositCreate,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> EscrowAgreement:
    return escrow_service.deposit(db, escrow_id, payload, idempotency_key=idempotency_key)


@router.post("/{escrow_id}/mark-delivered", response_model=EscrowRead)
def mark_delivered(escrow_id: int, payload: EscrowActionPayload, db: Session = Depends(get_db)) -> EscrowAgreement:
    return escrow_service.mark_delivered(db, escrow_id, payload)


@router.post("/{escrow_id}/client-approve", response_model=EscrowRead)
def client_approve(
    escrow_id: int,
    payload: EscrowActionPayload | None = Body(default=None),
    db: Session = Depends(get_db),
) -> EscrowAgreement:
    return escrow_service.client_approve(db, escrow_id, payload)


@router.post("/{escrow_id}/client-reject", response_model=EscrowRead)
def client_reject(
    escrow_id: int,
    payload: EscrowActionPayload | None = Body(default=None),
    db: Session = Depends(get_db),
) -> EscrowAgreement:
    return escrow_service.client_reject(db, escrow_id, payload)


@router.post("/{escrow_id}/check-deadline", response_model=EscrowRead)
def check_deadline(escrow_id: int, db: Session = Depends(get_db)) -> EscrowAgreement:
    return escrow_service.check_deadline(db, escrow_id)


@router.get("/{escrow_id}", response_model=EscrowRead)
def read_escrow(escrow_id: int, db: Session = Depends(get_db)) -> EscrowAgreement:
    agreement = db.get(EscrowAgreement, escrow_id)
    if not agreement:
        raise HTTPException(status_code=404, detail=error_response("ESCROW_NOT_FOUND", "Escrow not found."))
    return agreement
