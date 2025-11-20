"""Services handling PSP webhook callbacks."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Mapping

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.payment import Payment, PaymentStatus
from app.models.psp_webhook import PSPWebhookEvent
from app.models.audit import AuditLog
from app.services.payments import finalize_payment_settlement
from app.utils.audit import sanitize_payload_for_audit
from app.utils.errors import error_response
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

MAX_WEBHOOK_AGE_SECONDS = 120


def _current_settings():
    return get_settings()


def _current_secrets() -> tuple[str | None, str | None]:
    settings = _current_settings()
    return settings.psp_webhook_secret, settings.psp_webhook_secret_next


def _masked_secret_status(secrets_info: Mapping[str, str | None]) -> dict[str, str | None]:
    """Return deterministic markers instead of raw secrets for logging."""

    masked: dict[str, str | None] = {}
    for name, secret in secrets_info.items():
        if not secret:
            masked[name] = None
            continue

        digest = hashlib.sha256(secret.encode()).hexdigest()[:8]
        masked[name] = f"sha256:{digest}"
    return masked


def _get_header(headers: Mapping[str, str], key: str) -> str | None:
    for h_key, value in headers.items():
        if h_key.lower() == key.lower():
            return value
    return None


def _compute_webhook_signature(secret: str, body: bytes, timestamp: str) -> str:
    """Compute HMAC-SHA256 signature for the webhook payload."""

    msg = f"{timestamp}.{body.decode('utf-8')}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_psp_webhook_signature(raw_body: bytes, headers: Mapping[str, str]) -> None:
    """Validate PSP webhook signature and timestamp and raise on failure."""

    settings = _current_settings()
    provided_sig = _get_header(headers, "X-PSP-Signature")
    ts = _get_header(headers, "X-PSP-Timestamp")

    secrets = [s for s in (settings.psp_webhook_secret, settings.psp_webhook_secret_next) if s]
    secrets_info = {
        "primary": settings.psp_webhook_secret,
        "secondary": settings.psp_webhook_secret_next,
    }
    if not secrets:
        logger.error(
            "PSP webhook secrets are not configured",
            extra={"psp_secret_status": _masked_secret_status(secrets_info)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                "WEBHOOK_SECRET_NOT_CONFIGURED",
                "PSP webhook secrets are not configured.",
            ),
        )

    if not provided_sig or not ts:
        logger.warning(
            "Missing PSP signature or timestamp",
            extra={"psp_secret_status": _masked_secret_status(secrets_info)},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response(
                "WEBHOOK_SIGNATURE_MISSING",
                "Signature or timestamp header missing.",
            ),
        )

    ts_seconds: int | None = None
    try:
        ts_seconds = int(float(ts))
    except (TypeError, ValueError):
        try:
            ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            ts_seconds = int(ts_dt.timestamp())
        except Exception:  # noqa: BLE001
            logger.warning(
                "Invalid PSP webhook timestamp format",
                extra={"psp_secret_status": _masked_secret_status(secrets_info)},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_response(
                    "WEBHOOK_TIMESTAMP_INVALID",
                    "Invalid timestamp format.",
                ),
            )

    now = int(time.time())
    age = abs(now - ts_seconds)
    if age > MAX_WEBHOOK_AGE_SECONDS:
        logger.warning(
            "PSP webhook timestamp outside allowed window",
            extra={"psp_secret_status": _masked_secret_status(secrets_info), "age": age},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response(
                "WEBHOOK_TIMESTAMP_OUT_OF_RANGE",
                "Webhook timestamp is outside allowed window.",
            ),
        )

    for secret in secrets:
        expected = _compute_webhook_signature(secret, raw_body, ts)
        if hmac.compare_digest(expected, provided_sig):
            return

    logger.warning(
        "PSP webhook signature mismatch",
        extra={"psp_secret_status": _masked_secret_status(secrets_info)},
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=error_response(
            "WEBHOOK_SIGNATURE_INVALID",
            "Invalid PSP webhook signature.",
        ),
    )


def register_psp_event_or_raise_replay(db: Session, provider: str, event_id: str) -> None:
    """Detect PSP webhook replay attempts using provider/event_id pairs."""

    if not event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(
                "MISSING_EVENT_ID",
                "PSP webhook event_id is missing.",
            ),
        )

    existing = (
        db.query(PSPWebhookEvent)
        .execution_options(populate_existing=True)
        .filter(
            PSPWebhookEvent.provider == provider,
            PSPWebhookEvent.event_id == event_id,
        )
        .one_or_none()
    )
    if existing:
        logger.warning("Replay detected for PSP webhook", extra={"event_id": event_id, "provider": provider})
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("WEBHOOK_REPLAY", "Duplicate PSP webhook event detected."),
        )


def handle_event(
    db: Session,
    *,
    provider: str,
    event_id: str,
    psp_ref: str | None,
    kind: str,
    payload: dict[str, Any],
) -> PSPWebhookEvent:
    """Persist and process a PSP webhook event in an idempotent manner."""

    register_psp_event_or_raise_replay(db, provider, event_id)

    event = PSPWebhookEvent(
        provider=provider,
        event_id=event_id,
        psp_ref=psp_ref,
        kind=kind,
        raw_json=payload,
        received_at=utcnow(),
    )
    try:
        db.add(event)
        db.flush()
    except IntegrityError:
        db.rollback()
        logger.warning("Replay detected for PSP webhook", extra={"event_id": event_id, "provider": provider})
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("WEBHOOK_REPLAY", "Duplicate PSP webhook event detected."),
        )

    if kind in {"payment.settled", "payment_succeeded"}:
        _mark_payment_settled(
            db,
            psp_ref=psp_ref,
            provider=provider,
            event_id=event_id,
            status=kind,
        )
    elif kind in {"payment.failed", "payment_failed"}:
        _mark_payment_error(db, psp_ref=psp_ref)

    event.processed_at = utcnow()
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _mark_payment_settled(
    db: Session,
    *,
    psp_ref: str | None,
    provider: str,
    event_id: str,
    status: str,
) -> None:
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
        source="psp_webhook",
        extra={
            "psp_ref": psp_ref,
            "provider": provider,
            "event_id": event_id,
            "psp_status": status,
        },
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


__all__ = ["handle_event", "verify_psp_webhook_signature", "register_psp_event_or_raise_replay"]
