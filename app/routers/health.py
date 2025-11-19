"""Health check endpoint."""
from fastapi import APIRouter

from app.config import SCHEDULER_ENABLED, get_settings
from app.core.runtime_state import is_scheduler_active
from app.services.ai_proof_flags import ai_enabled

router = APIRouter(prefix="/health", tags=["health"])


def _secret_status(primary: str | None, secondary: str | None) -> str:
    if primary and secondary:
        return "ok"
    if primary or secondary:
        return "partial"
    return "missing"


@router.get("", summary="Health check")
def healthcheck() -> dict[str, object]:
    """Return a simple health payload with AI/OCR telemetry."""

    settings = get_settings()
    primary_secret = settings.psp_webhook_secret
    secondary_secret = settings.psp_webhook_secret_next
    return {
        "status": "ok",
        "psp_webhook_configured": bool(primary_secret or secondary_secret),
        "psp_webhook_secret_status": _secret_status(primary_secret, secondary_secret),
        "ocr_enabled": bool(settings.INVOICE_OCR_ENABLED),
        "ai_proof_enabled": ai_enabled(),
        "scheduler_config_enabled": SCHEDULER_ENABLED,
        "scheduler_running": is_scheduler_active(),
    }
