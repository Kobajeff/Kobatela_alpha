"""Usage mandate ORM model."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, Enum as SqlEnum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UsageMandateStatus(str, Enum):
    """Lifecycle statuses for usage mandates."""

    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"


class UsageMandate(Base):
    """Mandate linking a sender to a beneficiary with conditional usage limits."""

    __tablename__ = "usage_mandates"
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_usage_mandate_non_negative"),
    )

    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    beneficiary_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2, asdecimal=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    allowed_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("spend_categories.id"), nullable=True, index=True
    )
    allowed_merchant_id: Mapped[int | None] = mapped_column(
        ForeignKey("merchants.id"), nullable=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[UsageMandateStatus] = mapped_column(
        SqlEnum(UsageMandateStatus, name="usage_mandate_status"),
        nullable=False,
        default=UsageMandateStatus.ACTIVE,
    )
