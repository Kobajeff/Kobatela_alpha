"""Schemas for proof entities."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class ProofCreate(BaseModel):
    escrow_id: int
    milestone_idx: int = Field(ge=0)
    type: str = Field(min_length=1, max_length=50)
    storage_url: str = Field(min_length=1, max_length=1024)
    sha256: str = Field(min_length=1, max_length=128)
    metadata: dict | None = None


class ProofRead(BaseModel):
    id: int
    escrow_id: int
    milestone_id: int
    type: str
    storage_url: str
    sha256: str
    metadata: dict | None = Field(default=None, validation_alias="metadata_")
    status: str
    created_at: datetime
    updated_at: datetime

    ai_risk_level: str | None = None
    ai_score: Decimal | None = None
    ai_flags: list[str] | None = None
    ai_explanation: str | None = None
    ai_checked_at: datetime | None = None
    ai_reviewed_by: str | None = None
    ai_reviewed_at: datetime | None = None

    invoice_total_amount: Decimal | None = None
    invoice_currency: str | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_serializer("ai_score", when_used="json")
    def _serialize_ai_score(self, value: Decimal | None):
        return float(value) if value is not None else None


class ProofDecision(BaseModel):
    decision: str = Field(
        pattern="^(approve|approved|reject|rejected)$",
        description="Decision outcome",
    )
    note: str | None = None
