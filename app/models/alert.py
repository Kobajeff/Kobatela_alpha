"""Alert model."""
from sqlalchemy import ForeignKey, JSON, String, Index
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Alert(Base):
    """Represents an operational alert."""

    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_created_at", "created_at"),)

    type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    message: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
