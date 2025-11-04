"""Schemas for proof entities."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProofCreate(BaseModel):
    escrow_id: int
    milestone_idx: int = Field(ge=0)
    type: str = Field(min_length=1, max_length=50)
    storage_url: str = Field(min_length=1, max_length=1024)
    sha256: str = Field(min_length=1, max_length=128)
    metadata_: dict | None = None


class ProofRead(BaseModel):
    id: int
    escrow_id: int
    milestone_id: int
    type: str
    storage_url: str
    sha256: str
    metadata_: dict | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
