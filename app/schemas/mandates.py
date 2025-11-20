"""Pydantic schemas for usage mandates."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.usage_mandate import UsageMandateStatus


class UsageMandateBase(BaseModel):
    sender_id: int = Field(gt=0)
    beneficiary_id: int = Field(gt=0)
    total_amount: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    allowed_category_id: int | None = Field(default=None, gt=0)
    allowed_merchant_id: int | None = Field(default=None, gt=0)
    expires_at: datetime

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("expires_at")
    @classmethod
    def _ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class UsageMandateCreate(UsageMandateBase):
    """Payload schema to create a usage mandate."""


class UsageMandateRead(UsageMandateBase):
    """Response schema for usage mandates."""

    id: int
    status: UsageMandateStatus
    model_config = ConfigDict(from_attributes=True)
