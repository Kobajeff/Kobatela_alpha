"""API routes for usage mandates."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.mandates import UsageMandateCreate, UsageMandateRead
from app.models.api_key import ApiScope
from app.security import require_scope
from app.services import mandates as mandate_service

router = APIRouter(
    prefix="/mandates",
    tags=["mandates"],
    dependencies=[Depends(require_scope({ApiScope.sender}))],
)


@router.post("", response_model=UsageMandateRead, status_code=status.HTTP_201_CREATED)
def create_mandate(payload: UsageMandateCreate, db: Session = Depends(get_db)) -> UsageMandateRead:
    """Create a new usage mandate."""

    return mandate_service.create_mandate(db, payload)


@router.post("/cleanup", status_code=status.HTTP_202_ACCEPTED)
def cleanup_expired_mandates(db: Session = Depends(get_db)) -> dict[str, int]:
    """Expire mandates that passed their validity window."""

    expired = mandate_service.close_expired_mandates(db)
    return {"expired": expired}
