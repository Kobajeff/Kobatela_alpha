"""Health check endpoint."""
from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Health check")
def healthcheck() -> dict[str, str]:
    """Return a simple health payload."""

    return {"status": "ok"}
