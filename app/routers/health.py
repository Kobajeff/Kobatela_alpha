"""Health check endpoint."""
from fastapi import APIRouter

from app.config import SCHEDULER_ENABLED, get_settings
from app.core.runtime_state import is_scheduler_active

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Health check")
def healthcheck() -> dict[str, object]:
    """Return a simple health payload."""

    settings = get_settings()
    if not settings.psp_webhook_secret and not settings.psp_webhook_secret_next:
        psp_status = "missing"
    elif not settings.psp_webhook_secret or not settings.psp_webhook_secret_next:
        psp_status = "partial"
    else:
        psp_status = "ok"
    return {
        "status": "ok",
        "psp_webhook_secret_status": psp_status,
        "scheduler_config_enabled": SCHEDULER_ENABLED,
        "scheduler_running": is_scheduler_active(),
    }
