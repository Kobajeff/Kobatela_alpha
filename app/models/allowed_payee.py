"""Allowed payee model definitions."""
from datetime import date

from sqlalchemy import Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AllowedPayee(Base):
    """Represents an allowed payee for conditional usage spending."""

    __tablename__ = "allowed_payees"
    __table_args__ = (UniqueConstraint("escrow_id", "payee_ref", name="uq_allowed_payee_ref"),)

    escrow_id: Mapped[int] = mapped_column(ForeignKey("escrow_agreements.id"), index=True, nullable=False)
    payee_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)

    daily_limit: Mapped[float | None] = mapped_column(Float(asdecimal=False), nullable=True)
    total_limit: Mapped[float | None] = mapped_column(Float(asdecimal=False), nullable=True)

    spent_today: Mapped[float] = mapped_column(Float(asdecimal=False), nullable=False, default=0.0)
    spent_total: Mapped[float] = mapped_column(Float(asdecimal=False), nullable=False, default=0.0)
    last_reset_at: Mapped[date | None] = mapped_column(nullable=True)
