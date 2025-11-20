"""Routes for PSP webhook handling."""
from __future__ import annotations

import hashlib
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.services import psp_webhooks
from app.utils.errors import error_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/psp", tags=["psp"])


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def psp_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    settings = get_settings()
    if not (settings.psp_webhook_secret or settings.psp_webhook_secret_next):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PSP webhook secret not configured",
        )

    raw_body = await request.body()
    headers = {k: v for k, v in request.headers.items()}

    timestamp = psp_webhooks.verify_psp_webhook_signature(raw_body, headers)

    payload = await request.json()
    event_id = (
        payload.get("event_id")
        or payload.get("id")
        or request.headers.get("X-PSP-Event-Id")
    )
    if not event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response("MISSING_EVENT_ID", "Webhook event_id is required."),
        )

    psp_webhooks.ensure_not_recent_replay(event_id, timestamp)

    kind = payload.get("type") or payload.get("event") or "unknown"
    provider = payload.get("provider") or "default"
    psp_ref = payload.get("psp_ref") or payload.get("payment_reference") or request.headers.get("X-PSP-Ref")

    event = psp_webhooks.handle_event(
        db,
        provider=provider,
        event_id=event_id,
        psp_ref=psp_ref,
        kind=kind,
        payload=payload,
    )
    logger.info(
        "PSP webhook processed",
        extra={"event_id": event.event_id, "kind": event.kind, "provider": event.provider},
    )
    return {"ok": "true", "event_id": event.event_id, "processed_at": event.processed_at.isoformat()}


__all__ = ["router"]
