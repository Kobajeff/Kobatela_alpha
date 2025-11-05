"""PSP webhook persistence models."""
from datetime import datetime

from sqlalchemy import DateTime, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PSPWebhookEvent(Base):
    """Represents an incoming PSP webhook event for idempotent processing."""

    __tablename__ = "psp_webhook_events"
    __table_args__ = (UniqueConstraint("event_id", name="uq_psp_event_id"),)

    event_id: Mapped[str] = mapped_column(String(100), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    psp_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    raw_json: Mapped[dict] = mapped_column(JSON, nullable=False)
