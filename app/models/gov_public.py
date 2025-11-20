"""Models for KCT Public Sector lite."""
import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.utils.time import utcnow
from .base import Base


class GovEntityType(str, enum.Enum):
    MINISTRY = "ministry"
    AGENCY = "agency"
    ONG = "ong"
    OTHER = "other"


class GovEntity(Base):
    """Represents a government or NGO entity."""

    __tablename__ = "gov_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    type: Mapped[GovEntityType] = mapped_column(SqlEnum(GovEntityType, native_enum=False), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class GovProject(Base):
    """Represents a project under a government or NGO entity."""

    __tablename__ = "gov_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gov_entity_id: Mapped[int | None] = mapped_column(ForeignKey("gov_entities.id"), nullable=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    project_type: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="basic")
    domain: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class GovProjectMandate(Base):
    """Links escrows to a project mandate."""

    __tablename__ = "gov_project_mandates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gov_project_id: Mapped[int] = mapped_column(ForeignKey("gov_projects.id"), nullable=False)
    escrow_id: Mapped[int] = mapped_column(ForeignKey("escrow_agreements.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class GovProjectManager(Base):
    """Assigns a user as a manager/controller/auditor for a project."""

    __tablename__ = "gov_project_managers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gov_project_id: Mapped[int] = mapped_column(ForeignKey("gov_projects.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
