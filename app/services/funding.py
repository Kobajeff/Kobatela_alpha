"""Services for orchestrating escrow funding flows via Stripe."""
from __future__ import annotations

import logging
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuditLog, EscrowAgreement, FundingRecord, FundingStatus
from app.schemas import EscrowDepositCreate
from app.services import escrow as escrow_services
from app.services.psp_stripe import StripeClient
from app.utils.audit import sanitize_payload_for_audit
from app.utils.errors import error_response
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


def create_funding_session(
    db: Session, escrow: EscrowAgreement, *, amount: Decimal, currency: str
) -> tuple[FundingRecord, str]:
    """Create a funding PaymentIntent for an escrow and persist its record."""

    settings = get_settings()
    if not settings.STRIPE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_response("STRIPE_FUNDING_DISABLED", "Stripe funding not enabled."),
        )

    client = StripeClient(settings)
    payment_intent = client.create_funding_payment_intent(
        escrow=escrow, amount=amount, currency=currency
    )

    funding = FundingRecord(
        escrow_id=escrow.id,
        stripe_payment_intent_id=payment_intent.id,
        amount=amount,
        currency=currency,
        status=FundingStatus.CREATED,
    )
    db.add(funding)
    db.flush()
    db.add(
        AuditLog(
            actor="system",
            action="FUNDING_SESSION_CREATED",
            entity="FundingRecord",
            entity_id=funding.id,
            data_json=sanitize_payload_for_audit(
                {
                    "escrow_id": escrow.id,
                    "amount": str(amount),
                    "currency": currency,
                    "stripe_payment_intent_id": payment_intent.id,
                }
            ),
            at=utcnow(),
        )
    )
    db.commit()
    db.refresh(funding)
    logger.info(
        "Funding session created",
        extra={
            "escrow_id": escrow.id,
            "funding_id": funding.id,
            "stripe_payment_intent_id": payment_intent.id,
        },
    )
    return funding, payment_intent.client_secret


def mark_funding_succeeded(
    db: Session, *, stripe_payment_intent_id: str, amount: Decimal, currency: str
) -> FundingRecord | None:
    """Mark a funding attempt as succeeded and record the escrow deposit."""

    stmt = select(FundingRecord).where(
        FundingRecord.stripe_payment_intent_id == stripe_payment_intent_id
    )
    funding = db.scalars(stmt).first()
    if not funding:
        logger.warning(
            "Stripe funding success webhook with unknown intent",
            extra={"stripe_payment_intent_id": stripe_payment_intent_id},
        )
        return None

    if funding.status == FundingStatus.SUCCEEDED:
        logger.info(
            "Funding already marked as succeeded",
            extra={"funding_id": funding.id, "stripe_payment_intent_id": stripe_payment_intent_id},
        )
        return funding

    escrow_services.deposit(
        db,
        funding.escrow_id,
        EscrowDepositCreate(amount=amount),
        idempotency_key=f"stripe:{stripe_payment_intent_id}",
        actor="system",
    )

    funding.status = FundingStatus.SUCCEEDED
    db.add(
        AuditLog(
            actor="system",
            action="FUNDING_SUCCEEDED",
            entity="FundingRecord",
            entity_id=funding.id,
            data_json=sanitize_payload_for_audit(
                {
                    "escrow_id": funding.escrow_id,
                    "stripe_payment_intent_id": stripe_payment_intent_id,
                    "amount": str(amount),
                    "currency": currency,
                }
            ),
            at=utcnow(),
        )
    )
    db.commit()
    db.refresh(funding)
    logger.info(
        "Escrow funded via Stripe",
        extra={"funding_id": funding.id, "escrow_id": funding.escrow_id},
    )
    return funding


def mark_funding_failed(db: Session, *, stripe_payment_intent_id: str) -> FundingRecord | None:
    """Mark a funding attempt as failed if it exists and is pending."""

    stmt = select(FundingRecord).where(
        FundingRecord.stripe_payment_intent_id == stripe_payment_intent_id
    )
    funding = db.scalars(stmt).first()
    if not funding:
        logger.warning(
            "Stripe funding failure webhook with unknown intent",
            extra={"stripe_payment_intent_id": stripe_payment_intent_id},
        )
        return None

    if funding.status != FundingStatus.CREATED:
        logger.info(
            "Funding not in CREATED status; skipping failure update",
            extra={"funding_id": funding.id, "status": funding.status.value},
        )
        return funding

    funding.status = FundingStatus.FAILED
    db.add(
        AuditLog(
            actor="system",
            action="FUNDING_FAILED",
            entity="FundingRecord",
            entity_id=funding.id,
            data_json=sanitize_payload_for_audit(
                {
                    "escrow_id": funding.escrow_id,
                    "stripe_payment_intent_id": stripe_payment_intent_id,
                }
            ),
            at=utcnow(),
        )
    )
    db.commit()
    db.refresh(funding)
    logger.info(
        "Funding marked as failed",
        extra={"funding_id": funding.id, "escrow_id": funding.escrow_id},
    )
    return funding
