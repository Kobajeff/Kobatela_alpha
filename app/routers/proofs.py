"""Proof submission and decision endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.proof import ProofCreate, ProofDecision, ProofRead
from app.models.api_key import ApiKey, ApiScope
from app.security import require_scope
from app.services import proofs as proofs_service
from app.utils.audit import actor_from_api_key
from app.utils.errors import error_response

router = APIRouter(prefix="/proofs", tags=["proofs"])


@router.post("", response_model=ProofRead, status_code=status.HTTP_201_CREATED)
def submit_proof(
    payload: ProofCreate,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_scope({ApiScope.sender})),
):
    """Create a proof submission for a milestone."""

    actor = actor_from_api_key(api_key, fallback="apikey:unknown")
    return proofs_service.submit_proof(db, payload, actor=actor)


@router.post("/{proof_id}/decision", response_model=ProofRead)
def decide_proof(
    proof_id: int,
    decision: ProofDecision,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_scope({ApiScope.sender})),
):
    """Approve or reject a proof submission."""

    normalized = decision.decision.lower()
    actor = actor_from_api_key(api_key, fallback="apikey:unknown")
    if normalized == "approved":
        return proofs_service.approve_proof(db, proof_id, note=decision.note, actor=actor)
    if normalized == "rejected":
        return proofs_service.reject_proof(db, proof_id, note=decision.note, actor=actor)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=error_response("INVALID_DECISION", "Decision must be either approved or rejected."),
    )
