"""Allowed payee model definitions."""
from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AllowedPayee(Base):
    """Represents an allowed payee for conditional usage spending."""

    __tablename__ = "allowed_payees"
    __table_args__ = (
        UniqueConstraint("escrow_id", "payee_ref", name="uq_allowed_payee_ref"),
        CheckConstraint("daily_limit IS NULL OR daily_limit >= 0", name="ck_allowed_payee_daily_limit"),
        CheckConstraint("total_limit IS NULL OR total_limit >= 0", name="ck_allowed_payee_total_limit"),
        CheckConstraint("spent_today >= 0", name="ck_allowed_payee_spent_today_non_negative"),
        CheckConstraint("spent_total >= 0", name="ck_allowed_payee_spent_total_non_negative"),
    )

    escrow_id: Mapped[int] = mapped_column(ForeignKey("escrow_agreements.id"), index=True, nullable=False)
    payee_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)

    daily_limit: Mapped[float | None] = mapped_column(Numeric(18, 2, asdecimal=False), nullable=True)
    total_limit: Mapped[float | None] = mapped_column(Numeric(18, 2, asdecimal=False), nullable=True)

    spent_today: Mapped[float] = mapped_column(Numeric(18, 2, asdecimal=False), nullable=False, default=0.0)
    spent_total: Mapped[float] = mapped_column(Numeric(18, 2, asdecimal=False), nullable=False, default=0.0)
    last_reset_at: Mapped[date | None] = mapped_column(nullable=True)
