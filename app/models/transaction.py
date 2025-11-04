"""Transaction model."""
from enum import Enum as PyEnum

from sqlalchemy import CheckConstraint, Enum as SqlEnum, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class TransactionStatus(str, PyEnum):
    """Possible transaction statuses."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class Transaction(Base):
    """Represents a restricted wire transfer."""

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transaction_positive_amount"),
        Index("ix_transactions_created_at", "created_at"),
        Index("ix_transactions_status", "status"),
    )

    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    receiver_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float(asdecimal=False), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(SqlEnum(TransactionStatus), nullable=False, default=TransactionStatus.PENDING)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)

    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_transactions")
    receiver = relationship("User", foreign_keys=[receiver_id], back_populates="received_transactions")
