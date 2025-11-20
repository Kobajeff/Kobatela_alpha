# app/security.py
"""Security dependencies for API key validation and scope enforcement."""
from __future__ import annotations

from datetime import datetime, UTC
from typing import Callable, Set

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import DEV_API_KEY, DEV_API_KEY_ALLOWED, ENV
from app.db import get_db
from app.models.api_key import ApiKey, ApiScope
from app.models.user import User
from app.models.audit import AuditLog
from app.utils.apikey import find_valid_key
from app.utils.audit import sanitize_payload_for_audit
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
) -> ApiKey:
    """Validate API key tokens and return the corresponding row."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response("NO_API_KEY", "API key required."),
        )

    # Gestion de la clé legacy (mode dev)
    if token == DEV_API_KEY:
        if not DEV_API_KEY_ALLOWED:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_response("LEGACY_KEY_FORBIDDEN", "Legacy dev key disabled."),
            )
        now = datetime.now(UTC)
        db.add(
            AuditLog(
                actor="legacy-apikey",
                action="LEGACY_API_KEY_USED",
                entity="ApiKey",
                entity_id=0,
                data_json=sanitize_payload_for_audit({"env": ENV}),
                at=now,
            )
        )
        db.commit()
        fake = ApiKey(
            id=0,
            name="__legacy__",
            prefix="legacy",
            key_hash="legacy",
            scope=ApiScope.admin,
            is_active=True,
            created_at=now,
            expires_at=None,
            last_used_at=now,
        )
        return fake

    # Clés normales (prefix + hash)
    key = find_valid_key(db, token)
    if key == "legacy":
        # Cas non attendu car déjà géré ci-dessus mais on garde par prudence.
        if not DEV_API_KEY_ALLOWED:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_response("LEGACY_KEY_FORBIDDEN", "Legacy dev key disabled."),
            )
        now = datetime.now(UTC)
        db.add(
            AuditLog(
                actor="legacy-apikey",
                action="LEGACY_API_KEY_USED",
                entity="ApiKey",
                entity_id=0,
                data_json=sanitize_payload_for_audit({"env": ENV}),
                at=now,
            )
        )
        db.commit()
        return ApiKey(
            id=0,
            name="__legacy__",
            prefix="legacy",
            key_hash="legacy",
            scope=ApiScope.admin,
            is_active=True,
            created_at=now,
            expires_at=None,
            last_used_at=now,
        )

    if not isinstance(key, ApiKey) or not key.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response("UNAUTHORIZED", "Invalid or expired API key"),
        )

    # Book-keeping : last_used_at + audit
    now = datetime.now(UTC)
    key.last_used_at = now
    prefix = getattr(key, "prefix", None)
    payload = {"scope": key.scope.value}
    if prefix:
        payload["prefix"] = prefix
    db.add(
        AuditLog(
            actor=f"apikey:{key.id}",
            action="API_KEY_USED",
            entity="ApiKey",
            entity_id=key.id,
            data_json=sanitize_payload_for_audit(payload),
            at=now,
        )
    )
    db.commit()
    return key


def require_scope(allowed: Set[ApiScope]) -> Callable:
    """Enforce qu'une clé possède l'un des scopes autorisés."""

    if not allowed:
        raise RuntimeError("require_scope needs a non-empty set of ApiScope")

    def _dep(key: ApiKey = Depends(require_api_key)) -> ApiKey:
        if key.id == 0:
            return key
        if key.scope == ApiScope.admin or key.scope in allowed:
            return key
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response(
                "INSUFFICIENT_SCOPE",
                f"Requires one of: {[scope.value for scope in allowed]}",
            ),
        )

    return _dep


def require_public_user(
    api_key: ApiKey = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> User:
    """Ensure the API key is linked to a GOV/ONG user and return it."""

    user = getattr(api_key, "user", None)
    if user is None:
        user_id = getattr(api_key, "user_id", None)
        user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response("PUBLIC_USER_NOT_FOUND", "User not found for API key."),
        )

    if user.public_tag not in {"GOV", "ONG"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response(
                "PUBLIC_ACCESS_FORBIDDEN",
                "Access to KCT Public Sector is restricted to GOV/ONG accounts.",
            ),
        )

    return user


__all__ = ["require_api_key", "require_scope", "require_public_user"]
