"""Health check endpoint."""
from fastapi import APIRouter

from app.config import SCHEDULER_ENABLED, get_settings
from app.core.runtime_state import is_scheduler_active
from app.services.ai_proof_flags import ai_enabled

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Health check")
def healthcheck() -> dict[str, object]:
    """Return a simple health payload."""

    settings = get_settings()
    return {
        "status": "ok",
        "psp_webhook_configured": bool(settings.psp_webhook_secret or settings.psp_webhook_secret_next),
        "ocr_enabled": bool(settings.INVOICE_OCR_ENABLED),
        "ai_proof_enabled": ai_enabled(),
        "scheduler_config_enabled": SCHEDULER_ENABLED,
        "scheduler_running": is_scheduler_active(),
    }
