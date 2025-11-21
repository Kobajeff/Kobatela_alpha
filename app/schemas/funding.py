"""Funding schemas."""
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class FundingSessionRead(BaseModel):
    funding_id: int
    client_secret: str


class FundingRead(BaseModel):
    id: int
    escrow_id: int
    amount: Decimal
    currency: str
    status: str
    stripe_payment_intent_id: str

    model_config = ConfigDict(from_attributes=True)
