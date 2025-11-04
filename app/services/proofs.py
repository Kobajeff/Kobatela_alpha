"""Proof lifecycle services."""
import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Milestone, MilestoneStatus, Payment, PaymentStatus, Proof
from app.schemas.proof import ProofCreate
from app.services import payments as payments_service
from app.services.idempotency import get_existing_by_key
from app.utils.errors import error_response
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


def submit_proof(db: Session, payload: ProofCreate) -> Proof:
    """Submit a proof for the given escrow milestone."""

    milestone = _get_milestone_by_idx(db, payload.escrow_id, payload.milestone_idx)
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("MILESTONE_NOT_FOUND", "Milestone not found for escrow."),
        )

    if milestone.status != MilestoneStatus.WAITING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response(
                "MILESTONE_NOT_WAITING",
                "Milestone is not waiting for a proof submission.",
            ),
        )

    proof = Proof(
        escrow_id=payload.escrow_id,
        milestone_id=milestone.id,
        type=payload.type,
        storage_url=payload.storage_url,
        sha256=payload.sha256,
        metadata_=payload.metadata_,
        status="PENDING",
        created_at=utcnow(),
    )

    milestone.status = MilestoneStatus.PENDING_REVIEW
    db.add(proof)
    db.flush()
    db.add(
        AuditLog(
            actor="system",
            action="SUBMIT_PROOF",
            entity="Proof",
            entity_id=proof.id,
            data_json=payload.model_dump(),
            at=utcnow(),
        )
    )
    db.commit()
    db.refresh(proof)
    db.refresh(milestone)
    logger.info(
        "Proof submitted",
        extra={"proof_id": proof.id, "milestone_id": milestone.id, "escrow_id": payload.escrow_id},
    )
    return proof


def approve_proof(db: Session, proof_id: int, *, note: str | None = None) -> Proof:
    """Approve a proof and trigger payment execution."""

    proof = _get_proof_or_404(db, proof_id)
    if proof.status == "APPROVED":
        logger.info("Proof already approved", extra={"proof_id": proof.id})
        return proof
    if proof.status == "REJECTED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("PROOF_ALREADY_REJECTED", "Proof has already been rejected."),
        )

    milestone = db.get(Milestone, proof.milestone_id)
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("MILESTONE_MISSING", "Milestone linked to proof is missing."),
        )

    proof.status = "APPROVED"
    milestone.status = MilestoneStatus.APPROVED

    payment_key = f"milestone-{milestone.id}"
    payment = get_existing_by_key(db, Payment, payment_key)
    if payment is None:
        payment = Payment(
            escrow_id=proof.escrow_id,
            milestone_id=milestone.id,
            amount=milestone.amount,
            status=PaymentStatus.INITIATED,
            idempotency_key=payment_key,
        )
        db.add(payment)
        db.flush()
    else:
        logger.info("Reusing existing payment for milestone", extra={"payment_id": payment.id})

    db.add(
        AuditLog(
            actor="system",
            action="APPROVE_PROOF",
            entity="Proof",
            entity_id=proof.id,
            data_json={"proof_id": proof.id, "note": note},
            at=utcnow(),
        )
    )
    db.flush()

    payments_service.execute_payment(db, payment.id)
    db.refresh(proof)
    db.refresh(milestone)
    logger.info(
        "Proof approved",
        extra={"proof_id": proof.id, "payment_id": payment.id, "milestone_id": milestone.id},
    )
    return proof


def reject_proof(db: Session, proof_id: int, *, note: str | None = None) -> Proof:
    """Reject a proof submission and reset the milestone."""

    proof = _get_proof_or_404(db, proof_id)
    if proof.status == "REJECTED":
        logger.info("Proof already rejected", extra={"proof_id": proof.id})
        return proof
    if proof.status == "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("PROOF_ALREADY_APPROVED", "Approved proofs cannot be rejected."),
        )

    milestone = db.get(Milestone, proof.milestone_id)
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("MILESTONE_MISSING", "Milestone linked to proof is missing."),
        )

    proof.status = "REJECTED"
    milestone.status = MilestoneStatus.REJECTED

    db.add(
        AuditLog(
            actor="system",
            action="REJECT_PROOF",
            entity="Proof",
            entity_id=proof.id,
            data_json={"proof_id": proof.id, "note": note},
            at=utcnow(),
        )
    )
    db.commit()
    db.refresh(proof)
    db.refresh(milestone)
    logger.info(
        "Proof rejected",
        extra={"proof_id": proof.id, "milestone_id": milestone.id, "status": milestone.status.value},
    )
    return proof


def _get_proof_or_404(db: Session, proof_id: int) -> Proof:
    proof = db.get(Proof, proof_id)
    if proof is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("PROOF_NOT_FOUND", "Proof not found."),
        )
    return proof


def _get_milestone_by_idx(db: Session, escrow_id: int, milestone_idx: int) -> Milestone | None:
    stmt = select(Milestone).where(Milestone.escrow_id == escrow_id, Milestone.idx == milestone_idx)
    return db.scalars(stmt).first()


__all__ = ["submit_proof", "approve_proof", "reject_proof"]
