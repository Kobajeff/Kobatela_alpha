"""Scheduler lock ORM mapping."""
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SchedulerLock(Base):
    """Represents a distributed scheduler lock to avoid duplicate runs."""

    __tablename__ = "scheduler_locks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
