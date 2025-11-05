"""Escrow related models."""
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum as SqlEnum, Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class EscrowStatus(str, PyEnum):
    """Status of an escrow agreement."""

    DRAFT = "DRAFT"
    FUNDED = "FUNDED"
    RELEASABLE = "RELEASABLE"
    RELEASED = "RELEASED"
    REFUNDED = "REFUNDED"
    CANCELLED = "CANCELLED"


class EscrowAgreement(Base):
    """Represents an escrow agreement between client and provider."""

    __tablename__ = "escrow_agreements"

    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    amount_total: Mapped[float] = mapped_column(Float(asdecimal=False), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[EscrowStatus] = mapped_column(SqlEnum(EscrowStatus), default=EscrowStatus.DRAFT, nullable=False)
    release_conditions_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    deposits = relationship("EscrowDeposit", back_populates="escrow", cascade="all, delete-orphan")
    events = relationship("EscrowEvent", back_populates="escrow", cascade="all, delete-orphan")


class EscrowDeposit(Base):
    """Represents a deposit made toward an escrow agreement."""

    __tablename__ = "escrow_deposits"

    escrow_id: Mapped[int] = mapped_column(ForeignKey("escrow_agreements.id"), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float(asdecimal=False), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)

    escrow = relationship("EscrowAgreement", back_populates="deposits")


class EscrowEvent(Base):
    """Timeline event for an escrow agreement."""

    __tablename__ = "escrow_events"

    escrow_id: Mapped[int] = mapped_column(ForeignKey("escrow_agreements.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    data_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    escrow = relationship("EscrowAgreement", back_populates="events")
