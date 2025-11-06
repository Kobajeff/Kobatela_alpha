"""Transaction schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.certified import CertificationLevel
from app.models.transaction import TransactionStatus


class TransactionCreate(BaseModel):
    sender_id: int
    receiver_id: int
    amount: float = Field(gt=0)
    currency: str = Field(default="USD", pattern="^(USD|EUR)$")


class TransactionRead(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    amount: float
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
