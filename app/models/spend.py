"""Spend-related ORM models."""
from __future__ import annotations

from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, Enum as SqlEnum, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class SpendCategory(Base):
    """Represents a spend category used for usage policies."""

    __tablename__ = "spend_categories"

    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)

    merchants: Mapped[list["Merchant"]] = relationship(back_populates="category")


class Merchant(Base):
    """Represents a merchant that can receive purchases."""

    __tablename__ = "merchants"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("spend_categories.id"), nullable=True, index=True)
    is_certified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    category: Mapped[SpendCategory | None] = relationship(back_populates="merchants")
    purchases: Mapped[list["Purchase"]] = relationship(back_populates="merchant")


class AllowedUsage(Base):
    """Defines allowed usage rules per owner for merchants or categories."""

    __tablename__ = "allowed_usages"
    __table_args__ = (
        UniqueConstraint("owner_id", "merchant_id", name="uq_allowed_usage_merchant"),
        UniqueConstraint("owner_id", "category_id", name="uq_allowed_usage_category"),
        CheckConstraint(
            "(merchant_id IS NOT NULL AND category_id IS NULL) OR "
            "(merchant_id IS NULL AND category_id IS NOT NULL)",
            name="ck_allowed_usage_exactly_one_target",
        ),
    )

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchants.id"), nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("spend_categories.id"), nullable=True, index=True)


class PurchaseStatus(str, Enum):
    """Represents the lifecycle status for purchases."""

    COMPLETED = "COMPLETED"


class Purchase(Base):
    """Represents a merchant purchase made by a sender."""

    __tablename__ = "purchases"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_purchase_positive_amount"),
        Index("ix_purchases_created_at", "created_at"),
        Index("ix_purchases_status", "status"),
    )

    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id"), nullable=False, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("spend_categories.id"), nullable=True, index=True)
    amount: Mapped[float] = mapped_column(Float(asdecimal=False), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    status: Mapped[PurchaseStatus] = mapped_column(SqlEnum(PurchaseStatus), nullable=False, default=PurchaseStatus.COMPLETED)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)

    merchant: Mapped[Merchant] = relationship(back_populates="purchases")
    category: Mapped[SpendCategory | None] = relationship()
