"""Escrow agreement endpoints."""
from fastapi import APIRouter, Body, Depends, Header, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.api_key import ApiKey, ApiScope
from app.models.user import User
from app.models.audit import AuditLog
from app.models.escrow import EscrowAgreement
from app.schemas.escrow import EscrowActionPayload, EscrowCreate, EscrowDepositCreate, EscrowRead
from app.security import require_scope
from app.services import escrow as escrow_service
from app.utils.audit import actor_from_api_key
from app.utils.time import utcnow

router = APIRouter(
    prefix="/escrows",
    tags=["escrow"],
)


@router.post("", response_model=EscrowRead, status_code=status.HTTP_201_CREATED)
def create_escrow(
    payload: EscrowCreate,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_scope({ApiScope.sender})),
) -> EscrowAgreement:
    actor = actor_from_api_key(api_key, fallback="apikey:unknown")
    current_user = db.get(User, api_key.user_id) if getattr(api_key, "user_id", None) else None
    return escrow_service.create_escrow(db, payload, actor=actor, current_user=current_user)


@router.post("/{escrow_id}/deposit", response_model=EscrowRead, status_code=status.HTTP_200_OK)
def deposit(
    escrow_id: int,
    payload: EscrowDepositCreate,
    db: Session = Depends(get_db),
    idempotency_key: str = Header(alias="Idempotency-Key"),
    api_key: ApiKey = Depends(require_scope({ApiScope.sender})),
) -> EscrowAgreement:
    actor = actor_from_api_key(api_key, fallback="apikey:unknown")
    return escrow_service.deposit(
        db, escrow_id, payload, idempotency_key=idempotency_key, actor=actor
    )


@router.post("/{escrow_id}/mark-delivered", response_model=EscrowRead)
def mark_delivered(
    escrow_id: int,
    payload: EscrowActionPayload,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_scope({ApiScope.sender})),
) -> EscrowAgreement:
    actor = actor_from_api_key(api_key, fallback="apikey:unknown")
    return escrow_service.mark_delivered(db, escrow_id, payload, actor=actor)


@router.post("/{escrow_id}/client-approve", response_model=EscrowRead)
def client_approve(
    escrow_id: int,
    payload: EscrowActionPayload | None = Body(default=None),
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_scope({ApiScope.sender})),
) -> EscrowAgreement:
    actor = actor_from_api_key(api_key, fallback="apikey:unknown")
    return escrow_service.client_approve(db, escrow_id, payload, actor=actor)


@router.post("/{escrow_id}/client-reject", response_model=EscrowRead)
def client_reject(
    escrow_id: int,
    payload: EscrowActionPayload | None = Body(default=None),
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_scope({ApiScope.sender})),
) -> EscrowAgreement:
    actor = actor_from_api_key(api_key, fallback="apikey:unknown")
    return escrow_service.client_reject(db, escrow_id, payload, actor=actor)


@router.post("/{escrow_id}/check-deadline", response_model=EscrowRead)
def check_deadline(
    escrow_id: int,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_scope({ApiScope.sender})),
) -> EscrowAgreement:
    actor = actor_from_api_key(api_key, fallback="apikey:unknown")
    return escrow_service.check_deadline(db, escrow_id, actor=actor)


@router.get("/{escrow_id}", response_model=EscrowRead)
def read_escrow(
    escrow_id: int,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_scope({ApiScope.sender, ApiScope.support, ApiScope.admin})),
) -> EscrowAgreement:
    actor = actor_from_api_key(api_key, fallback="apikey:unknown")
    escrow = escrow_service.get_escrow(db, escrow_id, actor=actor)
    db.add(
        AuditLog(
            actor=actor,
            action="READ_ESCROW",
            entity="EscrowAgreement",
            entity_id=escrow_id,
            data_json={"endpoint": "GET /escrows/{id}"},
            at=utcnow(),
        )
    )
    db.commit()
    return escrow
