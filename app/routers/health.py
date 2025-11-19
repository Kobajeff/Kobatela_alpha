"""Health check endpoint."""
from fastapi import APIRouter

from app.config import SCHEDULER_ENABLED, settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Health check")
def healthcheck() -> dict[str, object]:
    """Return a simple health payload."""

    psp_ok = bool(settings.psp_webhook_secret or settings.psp_webhook_secret_next)
    return {
        "status": "ok",
        "psp_secrets_configured": psp_ok,
        "scheduler_enabled": SCHEDULER_ENABLED,
    }
