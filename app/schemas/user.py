"""User schemas."""
from pydantic import BaseModel, ConfigDict, EmailStr


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    is_active: bool = True


class UserRead(BaseModel):
    id: int
    username: str
    email: EmailStr
    is_active: bool
    stripe_account_id: str | None = None
    stripe_payout_enabled: bool = False
    stripe_payout_status: str | None = None

    model_config = ConfigDict(from_attributes=True)
