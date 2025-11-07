"""Schemas for spend management."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.spend import PurchaseStatus


class SpendCategoryCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=255)


class SpendCategoryRead(BaseModel):
    id: int
    code: str
    label: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MerchantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category_id: int | None = None
    is_certified: bool = False


class MerchantRead(BaseModel):
    id: int
    name: str
    category_id: int | None
    is_certified: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AllowedUsageCreate(BaseModel):
    owner_id: int
    merchant_id: int | None = None
    category_id: int | None = None

    @model_validator(mode="after")
    def validate_target(cls, values: "AllowedUsageCreate") -> "AllowedUsageCreate":
        has_merchant = values.merchant_id is not None
        has_category = values.category_id is not None
        if has_merchant == has_category:
            raise ValueError("Exactly one of merchant_id or category_id must be provided.")
        return values


class PurchaseCreate(BaseModel):
    sender_id: int
    merchant_id: int
    amount: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(default="USD", pattern="^(USD|EUR)$")
    category_id: int | None = None


class PurchaseRead(BaseModel):
    id: int
    sender_id: int
    merchant_id: int
    category_id: int | None
    amount: Decimal
    currency: str
    status: PurchaseStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
