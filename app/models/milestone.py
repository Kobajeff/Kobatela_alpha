"""Milestone model definitions."""
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import CheckConstraint, Enum as SqlEnum, Float, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym
from .base import Base


class MilestoneStatus(str, PyEnum):
    """Possible statuses for a milestone."""

    WAITING = "WAITING"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PAYING = "PAYING"
    PAID = "PAID"


class Milestone(Base):
    """Represents a milestone tied to an escrow agreement."""

    __tablename__ = "milestones"
    __table_args__ = (
        UniqueConstraint("escrow_id", "idx", name="uq_milestone_idx"),
        CheckConstraint("amount > 0", name="ck_milestone_positive_amount"),
        CheckConstraint("idx > 0", name="ck_milestone_positive_idx"),
        CheckConstraint(
            "geofence_radius_m IS NULL OR geofence_radius_m >= 0",
            name="ck_milestone_geofence_radius_non_negative",
        ),
    )

    escrow_id: Mapped[int] = mapped_column(ForeignKey("escrow_agreements.id"), nullable=False, index=True)
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    proof_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    proof_kind = synonym("proof_type")
    validator: Mapped[str] = mapped_column(String(50), nullable=False, default="SENDER")
    geofence_lat: Mapped[float | None] = mapped_column(Float(asdecimal=False), nullable=True)
    geofence_lng: Mapped[float | None] = mapped_column(Float(asdecimal=False), nullable=True)
    geofence_radius_m: Mapped[float | None] = mapped_column(Float(asdecimal=False), nullable=True)
    status: Mapped[MilestoneStatus] = mapped_column(SqlEnum(MilestoneStatus), nullable=False, default=MilestoneStatus.WAITING)

    proofs = relationship("Proof", back_populates="milestone", cascade="all, delete-orphan")
