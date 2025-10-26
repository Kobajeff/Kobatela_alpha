"""Utility helpers for standardized error responses."""
from typing import Any


def error_response(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a standardized error payload."""

    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return payload
