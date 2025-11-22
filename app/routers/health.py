"""Health check endpoint."""
from __future__ import annotations

import hashlib
import logging

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from fastapi import APIRouter

from app.config import Settings, get_settings
from app.core.runtime_state import is_scheduler_active
from app.db import get_engine
from app.services.ai_proof_advisor import get_ai_stats
from app.services.ai_proof_flags import ai_enabled
from app.services.invoice_ocr import get_ocr_stats
from app.services.scheduler_lock import describe_scheduler_lock

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)

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
    """Return 'ok' if the DB is reachable, 'error' otherwise."""

    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:  # noqa: BLE001
        logger.exception("DB health check failed")
        return "error"


def _expected_migration_head() -> str | None:
    try:
        config = Config("alembic.ini")
        script = ScriptDirectory.from_config(config)
        return script.get_current_head()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to load Alembic head revision")
        return None


def _migrations_status() -> tuple[bool, str]:
    expected_head = _expected_migration_head()
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            current = result.scalar()
        if expected_head and current == expected_head:
            return True, "up_to_date"
        if expected_head is None:
            return False, "unknown"
        return False, "out_of_date"
    except Exception:  # noqa: BLE001
        logger.exception("Migration check failed")
        return False, "unknown"


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
    db_ok = db_status == "ok"
    if db_ok:
        migration_ok, migration_status = _migrations_status()
    else:
        migration_ok, migration_status = False, "unknown"
    degraded = not (db_ok and migration_ok)
    ai_stats = get_ai_stats()
    return {
        "status": "degraded" if degraded else "ok",
        "psp_webhook_configured": bool(primary_secret or secondary_secret),
        "psp_webhook_secret_status": _secret_status(primary_secret, secondary_secret),
        "psp_webhook_secret_fingerprints": _psp_secret_fingerprints(settings),
        "stripe": {
            "enabled": bool(settings.STRIPE_ENABLED),
            "connect_enabled": bool(settings.STRIPE_CONNECT_ENABLED),
            "webhook_configured": bool(settings.STRIPE_WEBHOOK_SECRET),
            "api_key_configured": bool(settings.STRIPE_SECRET_KEY),
        },
        "ocr_enabled": bool(settings.INVOICE_OCR_ENABLED),
        "ai_proof_enabled": ai_enabled(),
        "ai_metrics": ai_stats,
        "ai_stats": ai_stats,
        "ocr_metrics": get_ocr_stats(),
        "scheduler_config_enabled": bool(settings.SCHEDULER_ENABLED),
        "scheduler_running": is_scheduler_active(),
        "db_ok": db_ok,
        "db_status": db_status,
        "migrations_ok": migration_ok,
        "migrations_status": migration_status,
        "scheduler_lock": describe_scheduler_lock(),
        "features": {
            "kct_public": {
                "enabled": True,
                "note": "Public Sector Lite (GovTrust/AidTrack) routes available for GOV/ONG accounts.",
            }
        },
    }
