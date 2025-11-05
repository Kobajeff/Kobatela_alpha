"""Audit log model."""
from datetime import datetime

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AuditLog(Base):
    """Represents an audit event in the system."""

    __tablename__ = "audit_logs"

    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[int] = mapped_column(nullable=False)
    data_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
