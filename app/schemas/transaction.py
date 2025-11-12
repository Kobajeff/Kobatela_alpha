"""Transaction schemas."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.certified import CertificationLevel
from app.models.transaction import TransactionStatus


class TransactionCreate(BaseModel):
    sender_id: int
    receiver_id: int
    amount: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(default="USD", pattern="^(USD|EUR)$")


class TransactionRead(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    amount: Decimal
    currency: str
    status: TransactionStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AllowlistCreate(BaseModel):
    owner_id: int
    recipient_id: int


class CertificationCreate(BaseModel):
    user_id: int
    level: CertificationLevel

    @field_validator("level", mode="before")
    @classmethod
    def _normalize_level(cls, value: str | CertificationLevel) -> CertificationLevel | str:
        """Allow case-insensitive enum values from clients."""

        if isinstance(value, str):
            return value.upper()
        return value
