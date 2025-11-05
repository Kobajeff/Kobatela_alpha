"""Services handling PSP webhook callbacks."""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.payment import Payment, PaymentStatus
from app.models.psp_webhook import PSPWebhookEvent
from app.models.audit import AuditLog
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

_SECRET = os.environ.get("PSP_WEBHOOK_SECRET", "")


def _verify_signature(body_bytes: bytes, signature: str) -> None:
    """Validate webhook signatures using the shared secret."""

    mac = hmac.new(_SECRET.encode(), body_bytes, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, signature or ""):
        logger.warning("Invalid PSP webhook signature")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")


def handle_event(
    db: Session,
    *,
    event_id: str,
    psp_ref: str | None,
    kind: str,
    payload: dict[str, Any],
) -> PSPWebhookEvent:
    """Persist and process a PSP webhook event in an idempotent manner."""

    existing = db.query(PSPWebhookEvent).filter(PSPWebhookEvent.event_id == event_id).one_or_none()
    if existing:
        logger.info("PSP webhook already processed", extra={"event_id": event_id})
        return existing

    event = PSPWebhookEvent(event_id=event_id, psp_ref=psp_ref, kind=kind, raw_json=payload)
    db.add(event)
    db.flush()

    if kind in {"payment.settled", "payment_succeeded"}:
        _mark_payment_settled(db, psp_ref=psp_ref)
    elif kind in {"payment.failed", "payment_failed"}:
        _mark_payment_error(db, psp_ref=psp_ref)

    event.processed_at = utcnow()
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _mark_payment_settled(db: Session, *, psp_ref: str | None) -> None:
    """Mark a payment as settled if a PSP confirmation references it."""

    if not psp_ref:
        logger.info("PSP settlement missing reference; skipping")
        return

    payment = db.query(Payment).filter(Payment.psp_ref == psp_ref).one_or_none()
    if payment is None:
        logger.info("PSP settlement for unknown payment", extra={"psp_ref": psp_ref})
        return

    if payment.status == PaymentStatus.SETTLED:
        logger.info("Payment already settled", extra={"payment_id": payment.id})
        return

    payment.status = PaymentStatus.SETTLED
    db.add(
        AuditLog(
            actor="psp",
            action="PAYMENT_SETTLED",
            entity="Payment",
            entity_id=payment.id,
            data_json={"psp_ref": psp_ref},
            at=utcnow(),
        )
    )
    db.add(payment)
    logger.info("Payment settled", extra={"payment_id": payment.id})


def _mark_payment_error(db: Session, *, psp_ref: str | None) -> None:
    """Mark a payment as errored when a PSP webhook reports a failure."""

    if not psp_ref:
        logger.info("PSP failure missing reference; skipping")
        return

    payment = db.query(Payment).filter(Payment.psp_ref == psp_ref).one_or_none()
    if payment is None:
        logger.info("PSP failure for unknown payment", extra={"psp_ref": psp_ref})
        return

    if payment.status == PaymentStatus.ERROR:
        logger.info("Payment already marked as error", extra={"payment_id": payment.id})
        return

    payment.status = PaymentStatus.ERROR
    db.add(
        AuditLog(
            actor="psp",
            action="PAYMENT_FAILED",
            entity="Payment",
            entity_id=payment.id,
            data_json={"psp_ref": psp_ref},
            at=utcnow(),
        )
    )
    db.add(payment)
    logger.info("Payment marked as error", extra={"payment_id": payment.id})


__all__ = ["_verify_signature", "handle_event"]
