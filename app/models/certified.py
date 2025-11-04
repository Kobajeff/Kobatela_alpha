"""Certified account model."""
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CertificationLevel(str, PyEnum):
    """Certification levels available for accounts."""

    BASIC = "basic"
    GOLD = "gold"


class CertifiedAccount(Base):
    """Represents a certified account."""

    __tablename__ = "certified_accounts"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    certified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    level: Mapped[CertificationLevel] = mapped_column(SqlEnum(CertificationLevel), nullable=False)
