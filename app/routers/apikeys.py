from __future__ import annotations

from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.api_key import ApiKey, ApiScope
from app.models.audit import AuditLog
from app.security import require_scope
from app.utils.errors import error_response

router = APIRouter(prefix="/apikeys", tags=["apikeys"])


class ApiKeyCreate(BaseModel):
    name: str
    key: str
    scope: ApiScope

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("name cannot be blank")
        return value.strip()

    @field_validator("key")
    @classmethod
    def key_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("key cannot be blank")
        return value.strip()


class ApiKeyRead(BaseModel):
    id: int
    name: str
    key: str
    scope: ApiScope
    is_active: bool
    last_used_at: datetime | None

    class Config:
        from_attributes = True


@router.post(
    "",
    response_model=ApiKeyRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_scope("admin"))],
)
def create_apikey(payload: ApiKeyCreate, db: Session = Depends(get_db)) -> ApiKey:
    row = ApiKey(
        name=payload.name,
        key=payload.key,
        scope=payload.scope,
        is_active=True,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:  # pragma: no cover - executed in tests when duplicates appear
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response("APIKEY_EXISTS", "Key or name already exists."),
        ) from exc
    db.refresh(row)

    audit = AuditLog(
        actor="admin",
        action="CREATE_API_KEY",
        entity="ApiKey",
        entity_id=row.id,
        data_json={"name": row.name, "scope": row.scope.value},
        at=datetime.now(UTC),
    )
    db.add(audit)
    db.commit()
    return row


@router.get(
    "/{api_key_id}",
    response_model=ApiKeyRead,
    dependencies=[Depends(require_scope("admin"))],
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
    dependencies=[Depends(require_scope("admin"))],
)
def revoke_apikey(api_key_id: int, db: Session = Depends(get_db)) -> Response:
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
                data_json={},
                at=datetime.now(UTC),
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
            data_json={"name": row.name},
            at=datetime.now(UTC),
        )
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
