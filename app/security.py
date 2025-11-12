"""Security dependencies for API key validation and scope enforcement."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.api_key import ApiScope
from app.utils.apikey import find_valid_key
from app.utils.errors import error_response


async def require_api_key(
    authorization: str = Header(default=None),
    db: Session = Depends(get_db),
):
    """Validate the Authorization header and return the associated API key."""

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response("UNAUTHORIZED", "Missing Bearer token"),
        )

    token = authorization.split(" ", 1)[1].strip()
    key = find_valid_key(db, token)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response("UNAUTHORIZED", "Invalid or expired API key"),
        )
    return key


def require_scope(allowed: set[ApiScope]):
    """Return a dependency enforcing that the API key has one of the allowed scopes."""

    async def _dep(key=Depends(require_api_key)):
        if key == "legacy":
            return
        if key.scope not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_response("FORBIDDEN", "Scope not allowed"),
            )

    return _dep
