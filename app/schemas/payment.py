"""Schemas for payment entities."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.payment import PaymentStatus


class PaymentRead(BaseModel):
    id: int
    escrow_id: int
    milestone_id: int | None
    amount: float
    psp_ref: str | None
    status: PaymentStatus
    idempotency_key: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
