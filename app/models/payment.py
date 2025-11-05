"""Payment model definitions."""
import enum

from sqlalchemy import Enum as SqlEnum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class PaymentStatus(str, enum.Enum):
    """Possible statuses for a payment."""

    PENDING = "PENDING"
    SENT = "SENT"
    SETTLED = "SETTLED"
    ERROR = "ERROR"
    REFUNDED = "REFUNDED"


class Payment(Base):
    """Represents a payment executed for an escrow or milestone."""

    __tablename__ = "payments"

    escrow_id: Mapped[int] = mapped_column(ForeignKey("escrow_agreements.id"), nullable=False, index=True)
    milestone_id: Mapped[int | None] = mapped_column(ForeignKey("milestones.id"), nullable=True, index=True)
    amount: Mapped[float] = mapped_column(Float(asdecimal=False), nullable=False)
    psp_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[PaymentStatus] = mapped_column(SqlEnum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)

    milestone = relationship("Milestone")
