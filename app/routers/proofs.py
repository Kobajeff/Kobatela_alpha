"""Proof submission and decision endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.proof import ProofCreate, ProofDecision, ProofRead
from app.security import require_api_key
from app.services import proofs as proofs_service
from app.utils.errors import error_response

router = APIRouter(prefix="/proofs", tags=["proofs"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=ProofRead, status_code=status.HTTP_201_CREATED)
def submit_proof(payload: ProofCreate, db: Session = Depends(get_db)):
    """Create a proof submission for a milestone."""

    return proofs_service.submit_proof(db, payload)


@router.post("/{proof_id}/decision", response_model=ProofRead)
def decide_proof(proof_id: int, decision: ProofDecision, db: Session = Depends(get_db)):
    """Approve or reject a proof submission."""

    normalized = decision.decision.lower()
    if normalized == "approved":
        return proofs_service.approve_proof(db, proof_id, note=decision.note)
    if normalized == "rejected":
        return proofs_service.reject_proof(db, proof_id, note=decision.note)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=error_response("INVALID_DECISION", "Decision must be either approved or rejected."),
    )
