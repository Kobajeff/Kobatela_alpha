# app/services/milestones.py
"""Milestone utility services."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.milestone import Milestone, MilestoneStatus

_OPEN_STATES = (
    MilestoneStatus.WAITING,
    MilestoneStatus.PENDING_REVIEW,
    MilestoneStatus.APPROVED,
    MilestoneStatus.PAYING,
)

def get_current_open_milestone(db: Session, escrow_id: int) -> Milestone | None:
    stmt = (
        select(Milestone)
        .where(Milestone.escrow_id == escrow_id)
        .where(Milestone.status.in_(_OPEN_STATES))
        .order_by(Milestone.idx.asc())
        .limit(1)
    )
    return db.scalars(stmt).first()

def all_milestones_paid(db: Session, escrow_id: int) -> bool:
    stmt = select(Milestone).where(Milestone.escrow_id == escrow_id)
    items = list(db.scalars(stmt).all())
    return len(items) > 0 and all(m.status == MilestoneStatus.PAID for m in items)

def open_next_waiting_milestone(db: Session, escrow_id: int) -> Milestone | None:
    stmt = (
        select(Milestone)
        .where(Milestone.escrow_id == escrow_id, Milestone.status.in_(_OPEN_STATES))
        .order_by(Milestone.idx.asc())
        .limit(1)
    )
    return db.scalars(stmt).first()

__all__ = ["all_milestones_paid", "get_current_open_milestone", "open_next_waiting_milestone"]
