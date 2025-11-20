"""Schemas for KCT Public Sector module."""
from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, constr


class PublicDomain(str, Enum):
    """Supported domains for public sector projects."""

    PUBLIC = "public"
    AID = "aid"


class GovProjectCreate(BaseModel):
    label: constr(min_length=3, max_length=255)
    project_type: constr(min_length=3, max_length=100)
    country: constr(min_length=2, max_length=2)
    city: str | None = None
    domain: PublicDomain
    gov_entity_id: int | None = None


class GovProjectRead(BaseModel):
    id: int
    label: str
    project_type: str
    country: str
    city: str | None
    domain: str
    status: str
    total_amount: Decimal
    released_amount: Decimal
    remaining_amount: Decimal
    current_milestone: int | None

    model_config = ConfigDict(from_attributes=True)


class GovProjectManagerCreate(BaseModel):
    user_id: int
    role: str
    is_primary: bool | None = None


class GovProjectMandateCreate(BaseModel):
    escrow_id: int
