"""Proof lifecycle services."""
import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    EscrowAgreement,
    EscrowEvent,
    EscrowStatus,
    Milestone,
    MilestoneStatus,
    Payment,
    PaymentStatus,
    Proof,
)
from app.schemas.proof import ProofCreate
from app.services import (
    milestones as milestones_service,
    payments as payments_service,
    rules as rules_service,
)
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

    current = milestones_service.get_current_open_milestone(db, payload.escrow_id)
    if current is None:
        logger.info(
            "No open milestone for proof submission",
            extra={"escrow_id": payload.escrow_id, "submitted_idx": payload.milestone_idx},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("NO_OPEN_MILESTONE", "No open milestone available for proof submission."),
        )
    if current.idx != milestone.idx:
        logger.info(
            "Proof submission rejected due to sequence error",
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

    if milestone.status != MilestoneStatus.WAITING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response(
                "MILESTONE_NOT_WAITING",
                "Milestone is not waiting for a proof submission.",
            ),
        )

    metadata_payload = dict(payload.metadata or {})
    review_reason: str | None = None
    auto_approve = False

    # Light rules (PHOTO case -> EXIF/GPS/time checks)
    if milestone.proof_type == "PHOTO":
        geofence = None
        if (
            getattr(milestone, "geofence_lat", None) is not None
            and getattr(milestone, "geofence_lng", None) is not None
            and getattr(milestone, "geofence_radius_m", None) is not None
        ):
            geofence = (
                float(milestone.geofence_lat),
                float(milestone.geofence_lng),
                float(milestone.geofence_radius_m),
            )

        ok, reason = rules_service.validate_photo_metadata(
            metadata=metadata_payload,
            geofence=geofence,
            max_skew_minutes=120,
        )
        if not ok:
            logger.info(
                "Photo proof metadata requires manual handling",
                extra={"reason": reason, "escrow_id": payload.escrow_id, "milestone_id": milestone.id},
            )
            # Provide both a single UPPERCASE reason and a list of lowercase reasons for tests
            if reason:
                metadata_payload["review_reasons"] = [reason.lower()]
                metadata_payload["review_reason"] = reason
        
    
            if reason == "OUT_OF_GEOFENCE":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=error_response("GEOFENCE_VIOLATION", "Photo outside geofence."),
                        )
            else:
                review_reason = reason
        else:
             auto_approve = True

    if review_reason is not None:
        metadata_payload["review_reason"] = review_reason

    # State transitions for milestone + proof
    proof_status = "APPROVED" if auto_approve else "PENDING"
    milestone.status = MilestoneStatus.APPROVED if auto_approve else MilestoneStatus.PENDING_REVIEW

    # Create the proof (single, clean constructor)
    proof = Proof(
        escrow_id=payload.escrow_id,
        milestone_id=milestone.id,
        type=payload.type,
        storage_url=payload.storage_url,
        sha256=payload.sha256,
        metadata_=metadata_payload or None,  # NOTE: column is metadata_
        status=proof_status,
        created_at=utcnow(),
    )
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

    escrow = db.get(EscrowAgreement, payload.escrow_id)
    if escrow is None:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("ESCROW_NOT_FOUND", "Escrow not found for proof submission."),
        )

    payment = None
    if auto_approve:
        logger.info(
            "Auto-approving photo proof",
            extra={"escrow_id": escrow.id, "milestone_id": milestone.id, "proof_id": proof.id},
        )
        try:
            payment = payments_service.execute_payout(
                db,
                escrow=escrow,
                milestone=milestone,
                amount=milestone.amount,
                idempotency_key=_milestone_payment_key(escrow.id, milestone.id, milestone.amount),
            )
        except ValueError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_response("INSUFFICIENT_ESCROW_BALANCE", str(exc)),
            ) from exc
        _handle_post_payment(db, escrow)
    else:
        db.commit()

    db.refresh(proof)
    db.refresh(milestone)
    logger.info(
        "Proof submitted",
        extra={
            "proof_id": proof.id,
            "milestone_id": milestone.id,
            "escrow_id": payload.escrow_id,
            "milestone_status": milestone.status.value,
            "auto_approved": auto_approve,
            "payment_id": getattr(payment, "id", None) if payment else None,
        },
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

    escrow = db.get(EscrowAgreement, proof.escrow_id)
    if escrow is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("ESCROW_NOT_FOUND", "Escrow not found for proof approval."),
        )

    proof.status = "APPROVED"
    milestone.status = MilestoneStatus.APPROVED

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

    try:
        # Idempotency key for this escrow/milestone payout
        payment_key = f"escrow:{escrow.id}:milestone:{milestone.id}:amount:{milestone.amount:.2f}"
        payment = payments_service.execute_payout(
            db,
            escrow=escrow,
            milestone=milestone,
            amount=milestone.amount,
            idempotency_key=payment_key,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("INSUFFICIENT_ESCROW_BALANCE", str(exc)),
        ) from exc

    _handle_post_payment(db, escrow)

    db.refresh(proof)
    db.refresh(milestone)
    logger.info(
        "Proof approved",
        extra={
            "proof_id": proof.id,
            "payment_id": payment.id,
            "milestone_id": milestone.id,
            "milestone_status": milestone.status.value,
        },
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


def _milestone_payment_key(escrow_id: int, milestone_id: int, amount: float) -> str:
    return f"pay|escrow:{escrow_id}|ms:{milestone_id}|amt:{amount}"


def _handle_post_payment(db: Session, escrow: EscrowAgreement) -> None:
    next_milestone = milestones_service.open_next_waiting_milestone(db, escrow.id)
    if next_milestone:
        logger.info(
            "Next milestone available",
            extra={
                "escrow_id": escrow.id,
                "milestone_id": next_milestone.id,
                "status": next_milestone.status.value,
            },
        )

    if milestones_service.all_milestones_paid(db, escrow.id):
        if escrow.status != EscrowStatus.RELEASED:
            escrow.status = EscrowStatus.RELEASED
            db.add(
                EscrowEvent(
                    escrow_id=escrow.id,
                    kind="CLOSED",
                    data_json={"reason": "all_milestones_paid"},
                    at=utcnow(),
                )
            )
            db.commit()
            db.refresh(escrow)
            logger.info("Escrow closed after all milestones paid", extra={"escrow_id": escrow.id})


__all__ = ["submit_proof", "approve_proof", "reject_proof"]
