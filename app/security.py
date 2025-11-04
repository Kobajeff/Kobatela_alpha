"""Simple API key security dependency."""
from fastapi import Depends, Header, HTTPException, status

from .config import get_settings


def get_api_key_header(authorization: str | None = Header(default=None)) -> str:
    """Extract and validate the bearer API key from Authorization header."""

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"error": {"code": "UNAUTHORIZED", "message": "Missing or invalid Authorization header."}})

    return authorization.removeprefix("Bearer ").strip()


def require_api_key(api_key: str = Depends(get_api_key_header)) -> None:
    """Ensure the provided API key matches settings."""

    settings = get_settings()
    if api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid API key."}})
