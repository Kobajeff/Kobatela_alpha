"""Health check endpoint."""
from __future__ import annotations

import hashlib
import logging

from sqlalchemy import text

from fastapi import APIRouter

from app.config import SCHEDULER_ENABLED, Settings, get_settings
from app.core.runtime_state import is_scheduler_active
from app.db import get_engine
from app.services.ai_proof_flags import ai_enabled
from app.services.scheduler_lock import describe_scheduler_lock

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)

LATEST_MIGRATION_REV = "4e1bd5489e1c"

def _psp_webhook_secret_status() -> str:
    """Return 'missing' | 'partial' | 'ok' depending on PSP webhook secrets."""
    settings = get_settings()
    primary = bool(getattr(settings, "PSP_WEBHOOK_SECRET", None))
    next_ = bool(getattr(settings, "PSP_WEBHOOK_SECRET_NEXT", None))

    # Case 1: aucun secret => missing
    if not primary and not next_:
        return "missing"

    # Case 2: secret principal OK, pas de next => ok (config simple)
    if primary and not next_:
        return "ok"

    # Case 3: tout le reste (next seul, ou rotation active) => partial
    return "partial"



def _secret_status(primary: str | None, secondary: str | None) -> str:
    if primary and secondary:
        return "ok"
    if primary or secondary:
        return "partial"
    return "missing"


def _db_status() -> str:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:  # noqa: BLE001
        logger.exception("DB health check failed")
        return "error"


def _migrations_status() -> str:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            current = result.scalar()
        if current == LATEST_MIGRATION_REV:
            return "up_to_date"
        return "out_of_date"
    except Exception:  # noqa: BLE001
        logger.exception("Migration check failed")
        return "unknown"


def _psp_secret_fingerprints(settings: Settings) -> dict[str, str | None]:
    def _fp(value: str | None) -> str | None:
        if not value:
            return None
        h = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return h[:8]

    return {
        "primary": _fp(settings.psp_webhook_secret),
        "next": _fp(settings.psp_webhook_secret_next),
    }


@router.get("", summary="Health check")
def healthcheck() -> dict[str, object]:
    """Return a simple health payload with AI/OCR telemetry."""

    settings = get_settings()
    primary_secret = settings.psp_webhook_secret
    secondary_secret = settings.psp_webhook_secret_next
    db_status = _db_status()
    migration_status = _migrations_status()
    degraded = db_status != "ok" or migration_status != "up_to_date"
    return {
        "status": "degraded" if degraded else "ok",
        "psp_webhook_configured": bool(primary_secret or secondary_secret),
        "psp_webhook_secret_status": _secret_status(primary_secret, secondary_secret),
        "psp_webhook_secret_fingerprints": _psp_secret_fingerprints(settings),
        "ocr_enabled": bool(settings.INVOICE_OCR_ENABLED),
        "ai_proof_enabled": ai_enabled(),
        "scheduler_config_enabled": bool(getattr(settings, "SCHEDULER_ENABLED", SCHEDULER_ENABLED)),
        "scheduler_running": is_scheduler_active(),
        "db_status": db_status,
        "migrations_status": migration_status,
        "scheduler_lock": describe_scheduler_lock(),
    }
