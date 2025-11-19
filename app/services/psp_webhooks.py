"""Services handling PSP webhook callbacks."""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.payment import Payment, PaymentStatus
from app.models.psp_webhook import PSPWebhookEvent
from app.models.audit import AuditLog
from app.services.payments import finalize_payment_settlement
from app.utils.audit import sanitize_payload_for_audit
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


def _current_settings():
    return get_settings()


def _current_secrets() -> tuple[str | None, str | None]:
    settings = _current_settings()
    return settings.psp_webhook_secret, settings.psp_webhook_secret_next


def _secrets_map() -> dict[str, str | None]:
    primary, secondary = _current_secrets()
    return {"primary": primary, "secondary": secondary}


def _masked_secret_status(secrets_info: dict[str, str | None]) -> dict[str, str | None]:
    """Return deterministic markers instead of raw secrets for logging."""

    masked: dict[str, str | None] = {}
    for name, secret in secrets_info.items():
        if not secret:
            masked[name] = None
            continue

        digest = hashlib.sha256(secret.encode()).hexdigest()[:8]
        masked[name] = f"sha256:{digest}"
    return masked


def _log_signature_failure(reason: str, *, secrets_info: dict[str, str | None]) -> None:
    logger.warning(
        "PSP signature verification failed",
        extra={"reason": reason, "psp_secret_status": _masked_secret_status(secrets_info)},
    )


def verify_signature(
    body_bytes: bytes,
    signature: str | None,
    timestamp: str | None,
    *,
    skew_seconds: int | None = None,
) -> tuple[bool, str]:
    """Validate webhook signatures with HMAC rotation and timestamp skew protection."""

    secrets_info = _secrets_map()
    secrets = [s for s in secrets_info.values() if s]
    if not secrets:
        _log_signature_failure("secret-missing", secrets_info=secrets_info)
        return False, "secret-missing"
    if not signature:
        _log_signature_failure("signature-missing", secrets_info=secrets_info)
        return False, "signature-missing"
    if not timestamp:
        _log_signature_failure("timestamp-missing", secrets_info=secrets_info)
        return False, "timestamp-missing"

    try:
        sent_ts = float(timestamp)
    except (TypeError, ValueError):
        _log_signature_failure("timestamp-invalid", secrets_info=secrets_info)
        return False, "timestamp-invalid"

    settings = _current_settings()
    drift = skew_seconds or settings.psp_webhook_max_drift_seconds or 300
    now = time.time()
    if abs(now - sent_ts) > drift:
        _log_signature_failure("timestamp-skew", secrets_info=secrets_info)
        return False, "timestamp-skew"

    payload = timestamp.encode() + b"." + body_bytes
    for secret in secrets:
        digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        if hmac.compare_digest(digest, signature):
            return True, ""

    _log_signature_failure("hmac-mismatch", secrets_info=secrets_info)
    return False, "hmac-mismatch"


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

    finalize_payment_settlement(
        db,
        payment,
        source="psp",
        extra={"psp_ref": psp_ref},
    )
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
            data_json=sanitize_payload_for_audit({"psp_ref": psp_ref}),
            at=utcnow(),
        )
    )
    db.add(payment)
    logger.info("Payment marked as error", extra={"payment_id": payment.id})


__all__ = ["handle_event", "verify_signature"]
