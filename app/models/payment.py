"""Payment model definitions."""
import enum
from decimal import Decimal

from sqlalchemy import CheckConstraint, Enum as SqlEnum, ForeignKey, Index, Numeric, String
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
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_positive_amount"),
        Index("ix_payments_created_at", "created_at"),
        Index("ix_payments_status", "status"),
        Index("ix_payments_escrow_status", "escrow_id", "status"),
        Index("ix_payments_idempotency_key", "idempotency_key"),
    )

    escrow_id: Mapped[int] = mapped_column(ForeignKey("escrow_agreements.id"), nullable=False, index=True)
    milestone_id: Mapped[int | None] = mapped_column(ForeignKey("milestones.id"), nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    psp_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    status: Mapped[PaymentStatus] = mapped_column(SqlEnum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)

    milestone = relationship("Milestone")
