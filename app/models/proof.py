"""Proof model definitions."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Proof(Base):
    """Represents supporting proof for a milestone."""

    __tablename__ = "proofs"

    escrow_id: Mapped[int] = mapped_column(
        ForeignKey("escrow_agreements.id"), nullable=False, index=True
    )
    milestone_id: Mapped[int] = mapped_column(
        ForeignKey("milestones.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Normalised invoice fields extracted from metadata/OCR
    invoice_total_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2, asdecimal=True),
        nullable=True,
    )
    invoice_currency: Mapped[str | None] = mapped_column(
        String(3),
        nullable=True,
    )

    # AI Proof Advisor fields
    ai_risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    ai_score: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3, asdecimal=True),
        nullable=True,
    )
    ai_flags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    ai_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    ai_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    milestone = relationship("Milestone", back_populates="proofs")
