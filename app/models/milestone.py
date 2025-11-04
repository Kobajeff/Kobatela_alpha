"""Milestone model definitions."""
from enum import Enum as PyEnum

from sqlalchemy import Enum as SqlEnum, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    __table_args__ = (UniqueConstraint("escrow_id", "idx", name="uq_milestone_idx"),)

    escrow_id: Mapped[int] = mapped_column(ForeignKey("escrow_agreements.id"), nullable=False, index=True)
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[float] = mapped_column(Float(asdecimal=False), nullable=False)
    proof_type: Mapped[str] = mapped_column(String(50), nullable=False)
    validator: Mapped[str] = mapped_column(String(50), nullable=False, default="SENDER")
    status: Mapped[MilestoneStatus] = mapped_column(SqlEnum(MilestoneStatus), nullable=False, default=MilestoneStatus.WAITING)

    proofs = relationship("Proof", back_populates="milestone", cascade="all, delete-orphan")
