"""Proof submission and decision endpoints."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.proof import ProofCreate, ProofDecision, ProofRead
from app.models.api_key import ApiKey, ApiScope
from app.security import require_scope
from app.services import proofs as proofs_service
from app.utils.audit import actor_from_api_key
from app.utils.masking import mask_proof_metadata

router = APIRouter(prefix="/proofs", tags=["proofs"])


def _proof_response(proof) -> ProofRead:
    """Serialize a proof while masking sensitive metadata."""

    payload = ProofRead.model_validate(proof, from_attributes=True)
    payload.metadata = mask_proof_metadata(payload.metadata)  # type: ignore[assignment]
    return payload


@router.post("", response_model=ProofRead, status_code=status.HTTP_201_CREATED)
def submit_proof(
    payload: ProofCreate,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_scope({ApiScope.sender})),
):
    """Create a proof submission for a milestone."""

    actor = actor_from_api_key(api_key, fallback="apikey:unknown")
    proof = proofs_service.submit_proof(db, payload, actor=actor)
    return _proof_response(proof)


@router.post("/{proof_id}/decision", response_model=ProofRead)
def decide_proof(
    proof_id: int,
    decision: ProofDecision,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_scope({ApiScope.support, ApiScope.admin})),
):
    """Approve or reject a proof submission."""

    actor = actor_from_api_key(api_key, fallback="apikey:unknown")
    proof = proofs_service.decide_proof(
        db,
        proof_id,
        decision=decision.decision,
        note=decision.note,
        actor=actor,
    )
    return _proof_response(proof)
