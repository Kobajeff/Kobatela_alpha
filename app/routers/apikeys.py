"""Endpoints for managing API keys."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.api_key import ApiKey, ApiScope
from app.security import require_scope
from app.utils.apikey import gen_key

router = APIRouter(prefix="/apikeys", tags=["apikeys"])


class CreateKeyIn(BaseModel):
    name: str
    scope: ApiScope
    days_valid: int | None = 90


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_scope({ApiScope.admin}))],
)
def create_api_key(payload: CreateKeyIn, db: Session = Depends(get_db)):
    raw, prefix, key_hash = gen_key()
    now = datetime.now(UTC)
    expires_at = (
        now + timedelta(days=payload.days_valid)
        if payload.days_valid
        else None
    )
    key = ApiKey(
        name=payload.name,
        prefix=prefix,
        key_hash=key_hash,
        scope=payload.scope,
        created_at=now,
        expires_at=expires_at,
        is_active=True,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return {"key": raw, "prefix": key.prefix, "scope": key.scope}
