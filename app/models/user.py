"""User model."""
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class User(Base):
    """Represents a Kobatella user."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    sent_transactions = relationship(
        "Transaction", back_populates="sender", foreign_keys="Transaction.sender_id", cascade="all, delete-orphan"
    )
    received_transactions = relationship(
        "Transaction", back_populates="receiver", foreign_keys="Transaction.receiver_id", cascade="all, delete-orphan"
    )
