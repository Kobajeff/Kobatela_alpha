"""Escrow schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.escrow import EscrowStatus


class EscrowCreate(BaseModel):
    client_id: int
    provider_id: int
    amount_total: float = Field(gt=0)
    currency: str = Field(pattern="^(USD|EUR)$")
    release_conditions: dict
    deadline_at: datetime


class EscrowRead(BaseModel):
    id: int
    client_id: int
    provider_id: int
    amount_total: float
    currency: str
    status: EscrowStatus
    release_conditions_json: dict
    deadline_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EscrowDepositCreate(BaseModel):
    amount: float = Field(gt=0)


class EscrowActionPayload(BaseModel):
    note: str | None = None
    proof_url: str | None = None
