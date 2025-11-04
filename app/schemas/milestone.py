"""Schemas for milestone entities."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.milestone import MilestoneStatus


class MilestoneCreate(BaseModel):
    escrow_id: int
    idx: int = Field(ge=0)
    label: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0)
    proof_type: str = Field(min_length=1, max_length=50)
    validator: str = Field(min_length=1, max_length=50)


class MilestoneRead(BaseModel):
    id: int
    escrow_id: int
    idx: int
    label: str
    amount: float
    proof_type: str
    validator: str
    status: MilestoneStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
