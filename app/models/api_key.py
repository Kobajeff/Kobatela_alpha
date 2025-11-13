from __future__ import annotations

from datetime import datetime, UTC
import enum

from sqlalchemy import Boolean, DateTime, Enum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ApiScope(str, enum.Enum):
    sender = "sender"
    support = "support"
    admin = "admin"


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    scope: Mapped[ApiScope] = mapped_column(
        Enum(ApiScope, name="apiscope"), nullable=False, default=ApiScope.sender
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (UniqueConstraint("key", name="uq_api_keys_key"),)


__all__ = ["ApiKey", "ApiScope"]
