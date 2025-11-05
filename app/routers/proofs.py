"""Proof submission and decision endpoints."""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.proof import ProofCreate, ProofDecision, ProofRead
from app.security import require_api_key
from app.services import milestones as milestones_service
from app.services import proofs as proofs_service
from app.utils.errors import error_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/proofs", tags=["proofs"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=ProofRead, status_code=status.HTTP_201_CREATED)
def submit_proof(payload: ProofCreate, db: Session = Depends(get_db)):
    """Create a proof submission for a milestone."""

    current = milestones_service.get_current_open_milestone(db, payload.escrow_id)
    if current is None:
        logger.info(
            "No open milestone for submission",
            extra={"escrow_id": payload.escrow_id, "submitted_idx": payload.milestone_idx},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("NO_OPEN_MILESTONE", "No open milestone available for proof submission."),
        )
    if current.idx != payload.milestone_idx:
        logger.info(
            "Proof submission blocked due to sequence error",
            extra={
                "escrow_id": payload.escrow_id,
                "expected_idx": current.idx,
                "submitted_idx": payload.milestone_idx,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response("SEQUENCE_ERROR", "Previous milestone not paid."),
        )

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
