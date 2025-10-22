"""Allowlist model."""
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AllowedRecipient(Base):
    """Represents a pre-approved recipient for a sender."""

    __tablename__ = "allowed_recipients"
    __table_args__ = (UniqueConstraint("owner_id", "recipient_id", name="uq_allowed_pair"),)

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
