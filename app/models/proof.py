"""Proof model definitions."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Proof(Base):
    """Represents supporting proof for a milestone."""

    __tablename__ = "proofs"

    escrow_id: Mapped[int] = mapped_column(ForeignKey("escrow_agreements.id"), nullable=False, index=True)
    milestone_id: Mapped[int] = mapped_column(ForeignKey("milestones.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str] = mapped_column(String(128), nullable=False)
    # Use a non-reserved attribute name while persisting to the "metadata" column.
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    milestone = relationship("Milestone", back_populates="proofs")
