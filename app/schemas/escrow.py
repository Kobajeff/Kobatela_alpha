"""Escrow schemas."""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.escrow import EscrowDomain, EscrowStatus


class EscrowCreate(BaseModel):
    client_id: int
    provider_id: int
    amount_total: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(pattern="^(USD|EUR)$")
    release_conditions: dict
    deadline_at: datetime
    domain: Literal["private", "public", "aid"] | None = None


class EscrowRead(BaseModel):
    id: int
    client_id: int
    provider_id: int
    amount_total: Decimal
    currency: str
    status: EscrowStatus
    domain: EscrowDomain
    release_conditions_json: dict
    deadline_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EscrowDepositCreate(BaseModel):
    amount: Decimal = Field(gt=Decimal("0"))


class EscrowActionPayload(BaseModel):
    note: str | None = None
    proof_url: str | None = None


class MilestoneCreate(BaseModel):
    label: str = Field(..., max_length=255)
    amount: Decimal
    currency: str = Field(..., min_length=3, max_length=3)
    sequence_index: int = Field(..., ge=1)
    proof_kind: str = "PHOTO"
    proof_requirements: Dict[str, Any] = Field(default_factory=dict)


class MilestoneRead(BaseModel):
    id: int
    escrow_id: int
    label: str
    amount: Decimal
    currency: str
    sequence_index: int = Field(validation_alias="idx")
    status: str
    proof_kind: str | None = None
    proof_requirements: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True
