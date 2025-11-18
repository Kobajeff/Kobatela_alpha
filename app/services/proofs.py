"""Proof lifecycle services."""
import logging
from decimal import Decimal
import os

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
from app.services.ai_proof_advisor import call_ai_proof_advisor
from app.services.ai_proof_flags import ai_enabled
from app.services.document_checks import compute_document_backend_checks
from app.services.invoice_ocr import enrich_metadata_with_invoice_ocr
from app.services.idempotency import get_existing_by_key
from app.utils.errors import error_response
from app.utils.time import utcnow

from typing import Any, Final

HARD_VALIDATION_ERRORS: Final = {
    "OUT_OF_GEOFENCE",
    "OUTSIDE_GEOFENCE",
    "GEOFENCE_VIOLATION",
    "TOO_OLD",
    "MISSING_EXIF_TIMESTAMP",
    "BAD_EXIF_TIMESTAMP",
}

AI_PROOF_ENABLED: Final[bool] = os.getenv("KCT_AI_PROOF_ENABLED", "0") == "1"
logger = logging.getLogger(__name__)


def submit_proof(
    db: Session, payload: ProofCreate, *, actor: str | None = None
) -> Proof:
    """Submit a proof for the given escrow milestone."""

    milestone = _get_milestone_by_idx(db, payload.escrow_id, payload.milestone_idx)
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("MILESTONE_NOT_FOUND", "Milestone not found for escrow."),
        )

    # NOTE: on NE vérifie PAS encore l’état (open milestone / WAITING / séquence).
    # On commence par valider la PHOTO pour pouvoir renvoyer 422 immédiatement
    # en cas d’erreur "dure" (géofence, exif manquant, trop vieux, etc.).

    metadata_payload = dict(payload.metadata or {})
    metadata_payload.pop("ai_assessment", None)
    ai_result: dict[str, Any] | None = None

    if payload.type in {"PDF", "INVOICE", "CONTRACT"}:
        metadata_payload = enrich_metadata_with_invoice_ocr(
            storage_url=payload.storage_url,
            existing_metadata=metadata_payload,
        )
    review_reason: str | None = None
    auto_approve = False

    # PHOTO: validations EXIF/GPS/âge + géofence
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

        # 1) Appel règle
        if payload.metadata is None:
            ok, reason = False, "MISSING_METADATA"
        else:
            ok, reason = rules_service.validate_photo_metadata(
                metadata=metadata_payload,
                geofence=geofence,
                max_age_minutes=120,
            )

        # 2) Normalisation
        norm = (reason or "").upper()
        if norm in {"OUT_OF_GEOFENCE", "OUTSIDE_GEOFENCE", "GEOFENCE_VIOLATION"} or "GEOFENCE" in norm:
                norm = "GEOFENCE_VIOLATION"

        if geofence is not None:
            lat = metadata_payload.get("gps_lat")
            lng = metadata_payload.get("gps_lng")
            if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
                from math import radians, sin, cos, asin, sqrt
                # center + radius (meters)
                c_lat, c_lng, radius_m = geofence
                # Haversine distance in meters
                R = 6_371_000.0
                dlat = radians(lat - c_lat)
                dlng = radians(lng - c_lng)
                a = sin(dlat / 2) ** 2 + cos(radians(c_lat)) * cos(radians(lat)) * sin(dlng / 2) ** 2
                d = 2 * R * asin(sqrt(a))
                if d > radius_m:
                    ok = False
                    reason = "GEOFENCE_VIOLATION"
                    norm = "GEOFENCE_VIOLATION"

        # 3) Erreurs dures -> 422 immédiat (avant toute logique d’état)
        if (not ok) and (norm in HARD_VALIDATION_ERRORS or "GEOFENCE" in norm):
            # toujours normaliser sur le code attendu par les tests
            err_code = "GEOFENCE_VIOLATION" if "GEOFENCE" in norm else (norm or "PHOTO_INVALID")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_response(err_code, "Photo failed validation."),
            )

        # 4) Cas "mous" -> revue manuelle (ex: source non fiable)
        if not ok:
            if norm in {"UNTRUSTED_SOURCE", "UNKNOWN_SOURCE", "UNTRUSTED_CAMERA"}:
                review_reason = "UNTRUSTED_SOURCE"
                metadata_payload["review_reason"] = review_reason
                metadata_payload["review_reasons"] = [review_reason.lower()]
            elif norm == "MISSING_METADATA":
                review_reason = "MISSING_METADATA"
                metadata_payload["review_reason"] = review_reason
                metadata_payload["review_reasons"] = [review_reason.lower()]
            else:
                # Filet de sécurité -> 422
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=error_response(norm or "PHOTO_INVALID", "Invalid photo metadata."),
                )
        else:
            auto_approve = True

            # 5) (NEW) Optional AI call for risk assessment (PHOTO only)
            if ai_enabled():
                try:
                    ai_context = {
                        "mandate_context": {
                            "escrow_id": payload.escrow_id,
                            "milestone_idx": payload.milestone_idx,
                            "milestone_label": milestone.label,
                            "milestone_amount": float(milestone.amount),
                            "proof_type": milestone.proof_type,
                            "proof_requirements": getattr(milestone, "proof_requirements", None),
                        },
                        "backend_checks": {
                            "has_metadata": payload.metadata is not None,
                            "geofence_configured": geofence is not None,
                            "validation_ok": bool(ok),
                            "validation_reason": reason,
                        },
                        "document_context": {
                            "type": payload.type,
                            "storage_url": payload.storage_url,
                            "sha256": payload.sha256,
                            "metadata": metadata_payload,
                        },
                    }

                    ai_result = call_ai_proof_advisor(
                        context=ai_context,
                        proof_storage_url=payload.storage_url,
                    )

                    # Store AI result in metadata of the proof
                    metadata_payload["ai_assessment"] = ai_result

                except Exception as exc:  # noqa: BLE001
                    logger.exception("AI proof advisor integration failed: %s", exc)
                    # Never block the proof because of AI issues
                    # -> fall back to normal behavior (no AI enrichment)
                    # (nothing else to do here)

    else:
        # NON-PHOTO proofs (PDF, invoices, contracts, other)
        # → always manual review (no auto_approve) BUT we call AI as an advisor if enabled.
        if ai_enabled():
            try:
                proof_reqs = getattr(milestone, "proof_requirements", None)

                backend_checks = compute_document_backend_checks(
                    proof_requirements=proof_reqs,
                    metadata=metadata_payload,
                )

                ai_context = {
                    "mandate_context": {
                        "escrow_id": payload.escrow_id,
                        "milestone_idx": payload.milestone_idx,
                        "milestone_label": milestone.label,
                        "milestone_amount": float(milestone.amount),
                        "proof_type": milestone.proof_type,
                        "proof_requirements": proof_reqs,
                    },
                    "backend_checks": backend_checks,
                    "document_context": {
                        "type": payload.type,  # e.g. "PDF", "INVOICE", "CONTRACT"
                        "storage_url": payload.storage_url,
                        "sha256": payload.sha256,
                        "metadata": metadata_payload,
                        # Future extension: "ocr_text": "..." once OCR is wired
                    },
                }

                ai_result = call_ai_proof_advisor(
                    context=ai_context,
                    proof_storage_url=payload.storage_url,
                )
                metadata_payload["ai_assessment"] = ai_result

            except Exception as exc:  # noqa: BLE001
                logger.exception("AI proof advisor (doc) integration failed: %s", exc)
                # Never block the proof because of AI issues
                # → continue with manual review as usual

    # -------------------------
    # Contrôles d’état APRES validation photo
    # -------------------------
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
            detail=error_response("MILESTONE_NOT_WAITING", "Milestone is not waiting for a proof submission."),
        )

    # Statuts preuve & milestone (une fois l’état validé)
    proof_status = "APPROVED" if auto_approve else "PENDING"
    milestone.status = MilestoneStatus.APPROVED if auto_approve else MilestoneStatus.PENDING_REVIEW

    # Création de la preuve
    proof = Proof(
        escrow_id=payload.escrow_id,
        milestone_id=milestone.id,
        type=payload.type,
        storage_url=payload.storage_url,
        sha256=payload.sha256,
        metadata_=metadata_payload or None,  # colonne = metadata_
        status=proof_status,
        created_at=utcnow(),
    )
    if ai_result:
        proof.ai_risk_level = ai_result.get("risk_level")
        proof.ai_score = ai_result.get("score")
        proof.ai_flags = list(ai_result.get("flags") or [])
        proof.ai_explanation = ai_result.get("explanation")
        proof.ai_checked_at = utcnow()
    db.add(proof)
    db.flush()

    db.add(
        AuditLog(
            actor=actor or "system",
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



def approve_proof(
    db: Session, proof_id: int, *, note: str | None = None, actor: str | None = None
) -> Proof:
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
            actor=actor or "system",
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


def reject_proof(
    db: Session, proof_id: int, *, note: str | None = None, actor: str | None = None
) -> Proof:
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
            actor=actor or "system",
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


def _milestone_payment_key(escrow_id: int, milestone_id: int, amount: Decimal) -> str:
    return f"pay|escrow:{escrow_id}|ms:{milestone_id}|amt:{amount:.2f}"


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
