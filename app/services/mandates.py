"""Usage mandate services."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.spend import Merchant, SpendCategory
from app.models.usage_mandate import UsageMandate, UsageMandateStatus
from app.models.user import User
from app.schemas.mandates import UsageMandateCreate
from app.utils.errors import error_response
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


def _audit_mandate(
    db: Session,
    *,
    actor: str,
    action: str,
    mandate_id: int,
    data: dict[str, Any] | None = None,
) -> None:
    """Persist an audit log entry for mandate lifecycle events."""

    audit = AuditLog(
        actor=actor,
        action=action,
        entity="UsageMandate",
        entity_id=mandate_id,
        data_json=data or {},
        at=utcnow(),
    )
    db.add(audit)


def _ensure_user(db: Session, user_id: int, *, role: str) -> None:
    if db.get(User, user_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("USER_NOT_FOUND", f"{role} user does not exist."),
        )


def _ensure_merchant(db: Session, merchant_id: int) -> None:
    if db.get(Merchant, merchant_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("MERCHANT_NOT_FOUND", "Merchant not found."),
        )


def _ensure_category(db: Session, category_id: int) -> None:
    if db.get(SpendCategory, category_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("CATEGORY_NOT_FOUND", "Spend category not found."),
        )


def create_mandate(db: Session, payload: UsageMandateCreate) -> UsageMandate:
    """Create a new usage mandate tying a sender to a beneficiary."""

    _ensure_user(db, payload.sender_id, role="Sender")
    _ensure_user(db, payload.beneficiary_id, role="Beneficiary")

    if payload.allowed_merchant_id is not None:
        _ensure_merchant(db, payload.allowed_merchant_id)
    if payload.allowed_category_id is not None:
        _ensure_category(db, payload.allowed_category_id)

    expires_at = payload.expires_at
    now = utcnow()
    if expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response("MANDATE_EXPIRES_IN_PAST", "Expiration date must be in the future."),
        )

    mandate = UsageMandate(
        sender_id=payload.sender_id,
        beneficiary_id=payload.beneficiary_id,
        total_amount=payload.total_amount,
        currency=payload.currency,
        allowed_category_id=payload.allowed_category_id,
        allowed_merchant_id=payload.allowed_merchant_id,
        expires_at=expires_at,
        status=UsageMandateStatus.ACTIVE,
    )
    db.add(mandate)
    db.flush()
    _audit_mandate(
        db,
        actor=f"sender:{payload.sender_id}",
        action="MANDATE_CREATED",
        mandate_id=mandate.id,
        data={
            "beneficiary_id": payload.beneficiary_id,
            "currency": payload.currency,
            "total_amount": str(payload.total_amount),
            "expires_at": expires_at.isoformat(),
        },
    )
    db.commit()
    db.refresh(mandate)
    logger.info(
        "Usage mandate created",
        extra={"mandate_id": mandate.id, "beneficiary_id": mandate.beneficiary_id},
    )
    return mandate


def close_expired_mandates(db: Session, *, reference_time: datetime | None = None) -> int:
    """Mark active mandates as expired when past their expiration date."""

    now = reference_time or utcnow()
    stmt = (
        select(UsageMandate)
        .where(UsageMandate.status == UsageMandateStatus.ACTIVE)
        .where(UsageMandate.expires_at <= now)
    )
    mandates = db.scalars(stmt).all()
    if not mandates:
        return 0

    for mandate in mandates:
        mandate.status = UsageMandateStatus.EXPIRED
        _audit_mandate(
            db,
            actor="system",
            action="MANDATE_EXPIRED",
            mandate_id=mandate.id,
            data={"expired_at": now.isoformat()},
        )

    db.commit()
    logger.info("Expired mandates closed", extra={"count": len(mandates)})
    return len(mandates)


def audit_mandate_event(
    db: Session,
    *,
    actor: str,
    action: str,
    mandate_id: int,
    data: dict[str, Any] | None = None,
) -> None:
    """Public helper so other services can log mandate events."""

    _audit_mandate(db, actor=actor, action=action, mandate_id=mandate_id, data=data)
