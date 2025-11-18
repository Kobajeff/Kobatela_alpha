"""Schemas for milestone entities."""
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.milestone import MilestoneStatus


PROOF_REQUIREMENTS_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://kobatela.app/schemas/milestone-proof-requirements.json",
    "title": "MilestoneProofRequirements",
    "type": "object",
    "description": (
        "Structured expectations for a milestone proof. The AI Proof Advisor reads this"
        " JSON to understand the human requirements (amounts, supplier, geography, dates)."
    ),
    "properties": {
        "file_type": {
            "type": "string",
            "description": "Expected asset type (PHOTO, INVOICE, CONTRACT, ANY).",
        },
        "expected_country": {"type": "string"},
        "expected_city": {"type": "string"},
        "expected_store_name": {"type": "string"},
        "expected_beneficiary": {"type": "string"},
        "expected_currency": {
            "type": "string",
            "pattern": "^[A-Z]{3}$",
            "description": "ISO 4217 currency code",
        },
        "expected_amount": {"type": "number"},
        "expected_quantity": {"type": "number"},
        "expected_unit_price": {"type": "number"},
        "expected_date_min": {"type": "string", "format": "date"},
        "expected_date_max": {"type": "string", "format": "date"},
        "expected_description": {"type": "string"},
        "gps_required": {"type": "boolean"},
        "notes": {"type": "string"},
    },
    "additionalProperties": True,
}


class MilestoneCreate(BaseModel):
    escrow_id: int
    idx: int = Field(gt=0)
    label: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=Decimal("0"))
    proof_type: str = Field(min_length=1, max_length=50)
    validator: str = Field(min_length=1, max_length=50)

    # JSON configuration describing the expected proof (optional)
    proof_requirements: dict[str, Any] | None = Field(default=None)

    geofence_lat: float | None = Field(default=None)
    geofence_lng: float | None = Field(default=None)
    geofence_radius_m: float | None = Field(default=None, ge=0)


class MilestoneRead(BaseModel):
    id: int
    escrow_id: int
    idx: int
    label: str
    amount: Decimal
    proof_type: str
    validator: str

    # Stored proof requirements (or null)
    proof_requirements: dict[str, Any] | None

    geofence_lat: float | None
    geofence_lng: float | None
    geofence_radius_m: float | None
    status: MilestoneStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
