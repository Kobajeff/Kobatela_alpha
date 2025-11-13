"""Security dependencies for API key validation and scope enforcement."""
from __future__ import annotations

from datetime import datetime, UTC
from typing import Callable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import API_SCOPES, DEV_API_KEY, DEV_API_KEY_ALLOWED
from app.db import get_db
from app.models.api_key import ApiKey, ApiScope
from app.models.audit import AuditLog
from app.utils.errors import error_response


def _extract_key(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str | None:
    """Extract an API key from either Authorization Bearer or X-API-Key."""

    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def require_api_key(
    db: Session = Depends(get_db),
    api_key: str | None = Depends(_extract_key),
) -> ApiKey:
    """Validate API keys, enforcing legacy restrictions and scope-aware usage."""

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response("NO_API_KEY", "API key required."),
        )

    if (not DEV_API_KEY_ALLOWED) and api_key == DEV_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response("LEGACY_KEY_FORBIDDEN", "Legacy dev key is disabled."),
        )

    if DEV_API_KEY_ALLOWED and api_key == DEV_API_KEY:
        return ApiKey(
            id=0,
            name="__dev__",
            key=DEV_API_KEY,
            scope=ApiScope.admin,
            is_active=True,
        )

    key_row = db.query(ApiKey).filter(ApiKey.key == api_key).first()
    if not key_row or not key_row.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response("INVALID_API_KEY", "Invalid or inactive API key."),
        )

    now = datetime.now(UTC)
    key_row.last_used_at = now
    audit = AuditLog(
        actor="apikey",
        action="API_KEY_USED",
        entity="ApiKey",
        entity_id=key_row.id,
        data_json={"scope": key_row.scope.value},
        at=now,
    )
    db.add(audit)
    db.commit()
    db.refresh(key_row)
    return key_row


def require_scope(required: str) -> Callable[[ApiKey], ApiKey]:
    """Return a dependency enforcing the specified scope (admin bypass)."""

    if required not in API_SCOPES:
        raise RuntimeError(f"Unknown scope '{required}'")
    required_scope = ApiScope(required)

    def _dep(key: ApiKey = Depends(require_api_key)) -> ApiKey:
        if key.id == 0:
            return key
        if key.scope == ApiScope.admin:
            return key
        if key.scope != required_scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_response("INSUFFICIENT_SCOPE", f"Scope '{required}' is required."),
            )
        return key

    return _dep


__all__ = ["require_api_key", "require_scope"]
