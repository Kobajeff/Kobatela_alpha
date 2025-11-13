# app/security.py
"""Security dependencies for API key validation and scope enforcement."""
from __future__ import annotations

from datetime import datetime, UTC
from typing import Callable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import DEV_API_KEY, DEV_API_KEY_ALLOWED
from app.db import get_db
from app.models.api_key import ApiKey, ApiScope
from app.models.audit import AuditLog
from app.utils.apikey import find_valid_key
from app.utils.errors import error_response


def _extract_key(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str | None:
    """Récupère la clé depuis Authorization: Bearer ... ou X-API-Key."""
    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def require_api_key(
    db: Session = Depends(get_db),
    token: str | None = Depends(_extract_key),
):
    """
    Valide la clé API.
    - Rejette la DEV_API_KEY si DEV_API_KEY_ALLOWED=False.
    - Si DEV_API_KEY_ALLOWED=True et token == DEV_API_KEY → renvoie le sentinelle "legacy".
    - Sinon, valide via find_valid_key(prefix+raw) et retourne la ligne ApiKey.
    - Met à jour last_used_at et crée un AuditLog sur usage.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response("UNAUTHORIZED", "Missing API key"),
        )

    # Gestion de la clé legacy (mode dev)
    if token == DEV_API_KEY:
        if not DEV_API_KEY_ALLOWED:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_response("LEGACY_KEY_FORBIDDEN", "Legacy dev key is disabled."),
            )
        # Bypass contrôlé : le scope sera validé dans require_scope (on tolère "legacy")
        return "legacy"

    # Clés normales (prefix + hash)
    key: ApiKey | None = find_valid_key(db, token)
    if not key or not key.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response("UNAUTHORIZED", "Invalid or expired API key"),
        )

    # Book-keeping : last_used_at + audit
    now = datetime.now(UTC)
    key.last_used_at = now
    db.add(
        AuditLog(
            actor="apikey",
            action="API_KEY_USED",
            entity="ApiKey",
            entity_id=key.id,
            data_json={"scope": key.scope.value},
            at=now,
        )
    )
    db.commit()
    return key


def require_scope(allowed: set[ApiScope]) -> Callable:
    """
    Enforce qu'une clé possède l'un des scopes autorisés.
    - "legacy" (DEV_API_KEY) passe toujours.
    - Admin bypass.
    """
    async def _dep(key=Depends(require_api_key)):
        if key == "legacy":
            return
        # key est une instance ApiKey
        if key.scope == ApiScope.admin:
            return
        if key.scope not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_response("INSUFFICIENT_SCOPE", "Scope not allowed"),
            )
    return _dep


__all__ = ["require_api_key", "require_scope"]
