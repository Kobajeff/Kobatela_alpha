"""Escrow agreement endpoints."""
from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.api_key import ApiKey, ApiScope
from app.models.audit import AuditLog
from app.models.escrow import EscrowAgreement
from app.models.milestone import Milestone, MilestoneStatus
from app.models.user import User
from app.schemas.escrow import (
    EscrowActionPayload,
    EscrowCreate,
    EscrowDepositCreate,
    EscrowRead,
    MilestoneCreate,
    MilestoneRead,
)
from app.schemas.funding import FundingSessionRead
from app.security import require_scope
from app.services import escrow as escrow_service
from app.services import funding as funding_service
from app.utils.audit import actor_from_api_key
from app.utils.time import utcnow

router = APIRouter(
    prefix="/escrows",
    tags=["escrow"],
)


def _get_escrow_or_404(db: Session, escrow_id: int) -> EscrowAgreement:
    escrow = db.get(EscrowAgreement, escrow_id)
    if escrow is None:
        raise HTTPException(status_code=404, detail="Escrow not found")
    return escrow


@router.post("", response_model=EscrowRead, status_code=status.HTTP_201_CREATED)
def create_escrow(
    payload: EscrowCreate,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_scope({ApiScope.sender})),
) -> EscrowAgreement:
    actor = actor_from_api_key(api_key, fallback="apikey:unknown")
    current_user: User | None = None
    user_id = getattr(api_key, "user_id", None)
    if user_id is not None:
        current_user = db.get(User, user_id)

    return escrow_service.create_escrow(
        db, payload, actor=actor, current_user=current_user
    )


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


@router.post(
    "/{escrow_id}/funding-session",
    response_model=FundingSessionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_funding_session(
    escrow_id: int,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_scope({ApiScope.sender, ApiScope.admin})),
) -> FundingSessionRead:
    actor = actor_from_api_key(api_key, fallback="apikey:unknown")
    escrow = escrow_service.get_escrow(db, escrow_id, actor=actor)
    funding_record, client_secret = funding_service.create_funding_session(
        db,
        escrow,
        amount=escrow.amount_total,
        currency=escrow.currency,
    )
    return FundingSessionRead(
        funding_id=funding_record.id,
        client_secret=client_secret,
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


@router.post(
    "/{escrow_id}/milestones",
    response_model=MilestoneRead,
    status_code=status.HTTP_201_CREATED,
)
def create_milestone_for_escrow(
    escrow_id: int,
    payload: MilestoneCreate,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_scope({ApiScope.admin})),
):
    escrow = _get_escrow_or_404(db, escrow_id)

    if payload.currency.upper() != escrow.currency.upper():
        raise HTTPException(
            status_code=400,
            detail="Milestone currency must match escrow currency",
        )

    existing_amount = (
        db.execute(
            select(func.coalesce(func.sum(Milestone.amount), 0))
            .where(Milestone.escrow_id == escrow.id)
        )
        .scalar_one()
    )

    if existing_amount + payload.amount > escrow.amount_total:
        raise HTTPException(
            status_code=400,
            detail="Total milestone amounts exceed escrow amount_total",
        )

    existing = db.execute(
        select(Milestone.id).where(
            Milestone.escrow_id == escrow.id,
            Milestone.idx == payload.sequence_index,
        )
    ).scalar_one_or_none()

    if existing is not None:
        raise HTTPException(
            status_code=400,
            detail="A milestone with this sequence_index already exists for this escrow",
        )

    milestone = Milestone(
        escrow_id=escrow.id,
        idx=payload.sequence_index,
        label=payload.label,
        amount=payload.amount,
        currency=payload.currency.upper(),
        status=MilestoneStatus.WAITING,
        proof_kind=payload.proof_kind,
        proof_requirements=payload.proof_requirements,
    )

    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    return milestone


@router.get(
    "/{escrow_id}/milestones",
    response_model=list[MilestoneRead],
    status_code=status.HTTP_200_OK,
)
def list_milestones_for_escrow(
    escrow_id: int,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_scope({ApiScope.sender, ApiScope.admin})),
):
    _get_escrow_or_404(db, escrow_id)

    milestones = (
        db.execute(
            select(Milestone)
            .where(Milestone.escrow_id == escrow_id)
            .order_by(Milestone.idx)
        )
        .scalars()
        .all()
    )
    return milestones


@router.get(
    "/milestones/{milestone_id}",
    response_model=MilestoneRead,
    status_code=status.HTTP_200_OK,
)
def get_milestone(
    milestone_id: int,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_scope({ApiScope.admin, ApiScope.sender})),
):
    milestone = db.get(Milestone, milestone_id)
    if milestone is None:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return milestone
