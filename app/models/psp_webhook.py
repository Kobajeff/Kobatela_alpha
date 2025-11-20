"""PSP webhook persistence models."""
from datetime import datetime

from sqlalchemy import DateTime, JSON, String, UniqueConstraint, func, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PSPWebhookEvent(Base):
    """Represents an incoming PSP webhook event for idempotent processing."""

    __tablename__ = "psp_webhook_events"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "event_id",
            name="uq_psp_webhook_events_provider_event_id",
        ),
        Index("ix_psp_webhook_events_received", "received_at"),
        Index("ix_psp_webhook_events_kind", "kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="default")
    event_id: Mapped[str] = mapped_column(String(100), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    psp_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    raw_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False
    )
