"""Funding record model definitions."""
import enum
from decimal import Decimal

from sqlalchemy import Enum as SqlEnum, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class FundingStatus(str, enum.Enum):
    """Possible statuses for a funding operation."""

    CREATED = "CREATED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class FundingRecord(Base):
    """Represents an incoming funding attempt for an escrow agreement."""

    __tablename__ = "fundings"
    __table_args__ = (
        UniqueConstraint(
            "stripe_payment_intent_id", name="uq_fundings_stripe_payment_intent_id"
        ),
        Index("ix_fundings_escrow_id", "escrow_id"),
        Index("ix_fundings_status", "status"),
        Index("ix_fundings_created_at", "created_at"),
    )

    escrow_id: Mapped[int] = mapped_column(
        ForeignKey("escrow_agreements.id"), nullable=False
    )
    stripe_payment_intent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[FundingStatus] = mapped_column(
        SqlEnum(FundingStatus), nullable=False, default=FundingStatus.CREATED
    )

    escrow = relationship("EscrowAgreement")
