"""Alert schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertRead(BaseModel):
    id: int
    type: str
    message: str
    actor_user_id: int | None
    payload_json: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
