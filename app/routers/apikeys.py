# app/routers/apikeys.py
from __future__ import annotations

from datetime import datetime, UTC, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.api_key import ApiKey, ApiScope
from app.models.audit import AuditLog
from app.security import require_scope
from app.utils.audit import sanitize_payload_for_audit
from app.utils.errors import error_response
from app.utils.apikey import gen_key

router = APIRouter(prefix="/apikeys", tags=["apikeys"])


# ------ Schemas ------

class CreateKeyIn(BaseModel):
    """Payload d'entrée pour créer une nouvelle clé (pas de champ 'key' ici)."""
    name: str
    scope: ApiScope
    days_valid: int | None = 90

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("name cannot be blank")
        return value.strip()


class ApiKeyCreateOut(BaseModel):
    """Réponse du POST /apikeys : on renvoie la clé brute UNE SEULE fois."""
    id: int
    name: str
    scope: ApiScope
    key: str
    expires_at: datetime | None


class ApiKeyRead(BaseModel):
    """Réponse des GET (jamais la clé)."""
    id: int
    name: str
    scope: ApiScope
    is_active: bool
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None

    class Config:
        from_attributes = True


# ------ Routes ------

@router.post(
    "",
    response_model=ApiKeyCreateOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_scope({ApiScope.admin}))],
)
def create_api_key(payload: CreateKeyIn, db: Session = Depends(get_db)) -> ApiKeyCreateOut:
    """Crée une clé API côté serveur et renvoie la valeur brute une seule fois."""
    raw, prefix, key_hash = gen_key()
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=payload.days_valid) if payload.days_valid else None

    row = ApiKey(
        name=payload.name,
        prefix=prefix,
        key_hash=key_hash,
        scope=payload.scope,
        created_at=now,
        expires_at=expires_at,
        is_active=True,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response("APIKEY_EXISTS", "Key name already exists."),
        ) from exc
    db.refresh(row)

    # Audit: création de clé
    db.add(
        AuditLog(
            actor="admin",
            action="CREATE_API_KEY",
            entity="ApiKey",
            entity_id=row.id,
            data_json=sanitize_payload_for_audit({"name": row.name, "scope": row.scope.value}),
            at=now,
        )
    )
    db.commit()

    return ApiKeyCreateOut(
        id=row.id,
        name=row.name,
        scope=row.scope,
        key=raw,               # ne sera plus jamais renvoyée
        expires_at=row.expires_at,
    )


@router.get(
    "/{api_key_id}",
    response_model=ApiKeyRead,
    dependencies=[Depends(require_scope({ApiScope.admin}))],
)
def get_apikey(api_key_id: int, db: Session = Depends(get_db)) -> ApiKey:
    row = db.get(ApiKey, api_key_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("APIKEY_NOT_FOUND", "API key not found."),
        )
    return row


@router.delete(
    "/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(require_scope({ApiScope.admin}))],
)
def revoke_apikey(api_key_id: int, db: Session = Depends(get_db)) -> Response:
    now = datetime.now(UTC)
    row = db.get(ApiKey, api_key_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("APIKEY_NOT_FOUND", "API key not found."),
        )

    if not row.is_active:
        db.add(
            AuditLog(
                actor="admin",
                action="REVOKE_API_KEY_NOOP",
                entity="ApiKey",
                entity_id=api_key_id,
                data_json=sanitize_payload_for_audit({}),
                at=now,
            )
        )
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    row.is_active = False
    db.add(row)
    db.add(
        AuditLog(
            actor="admin",
            action="REVOKE_API_KEY",
            entity="ApiKey",
            entity_id=api_key_id,
            data_json=sanitize_payload_for_audit({"name": row.name}),
            at=now,
        )
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

