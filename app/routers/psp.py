"""Routes for PSP webhook handling."""
from __future__ import annotations

import hashlib
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.services import psp_webhooks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/psp", tags=["psp"])


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def psp_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_psp_signature: str | None = Header(default=None),
    x_psp_timestamp: str | None = Header(default=None),
    x_psp_event_id: str | None = Header(default=None),
    x_psp_ref: str | None = Header(default=None),
) -> dict[str, str]:
    settings = get_settings()
    if not (settings.psp_webhook_secret or settings.psp_webhook_secret_next):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PSP webhook secret not configured",
        )

    body = await request.body()
    ok, reason = psp_webhooks.verify_signature(body, x_psp_signature, x_psp_timestamp)
    if not ok:
        logger.warning(
            "Invalid PSP webhook signature",
            extra={"reason": reason, "event_id": x_psp_event_id, "psp_ref": x_psp_ref},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid signature: {reason}")

    payload = await request.json()
    event_id = x_psp_event_id or payload.get("id") or payload.get("event_id")
    if not event_id:
        event_id = hashlib.sha1(body).hexdigest()

    kind = payload.get("type") or payload.get("event") or "unknown"
    psp_ref = x_psp_ref or payload.get("psp_ref") or payload.get("payment_reference")

    event = psp_webhooks.handle_event(
        db,
        event_id=event_id,
        psp_ref=psp_ref,
        kind=kind,
        payload=payload,
    )
    logger.info("PSP webhook processed", extra={"event_id": event.event_id, "kind": event.kind})
    return {"ok": "true", "event_id": event.event_id, "processed_at": event.processed_at.isoformat()}


__all__ = ["router"]
