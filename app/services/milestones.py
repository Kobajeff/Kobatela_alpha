"""Milestone utility services."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.milestone import Milestone, MilestoneStatus


def get_current_open_milestone(db: Session, escrow_id: int) -> Milestone | None:
    """Return the earliest milestone that is not yet fully paid."""

    stmt = (
        select(Milestone)
        .where(Milestone.escrow_id == escrow_id)
        .where(
            Milestone.status.in_(
                [
                    MilestoneStatus.WAITING,
                    MilestoneStatus.PENDING_REVIEW,
                    MilestoneStatus.APPROVED,
                    MilestoneStatus.PAYING,
                ]
            )
        )
        .order_by(Milestone.idx.asc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def all_milestones_paid(db: Session, escrow_id: int) -> bool:
    """Return True when all milestones for an escrow are marked as paid."""

    stmt = select(Milestone).where(Milestone.escrow_id == escrow_id)
    items = list(db.scalars(stmt).all())
    return len(items) > 0 and all(m.status == MilestoneStatus.PAID for m in items)


def open_next_waiting_milestone(db: Session, escrow_id: int) -> Milestone | None:
    """Return the next milestone that is not yet paid."""

    stmt = select(Milestone).where(Milestone.escrow_id == escrow_id).order_by(Milestone.idx.asc())
    milestones = list(db.scalars(stmt).all())
    for milestone in milestones:
        if milestone.status != MilestoneStatus.PAID:
            return milestone
    return None


__all__ = ["all_milestones_paid", "get_current_open_milestone", "open_next_waiting_milestone"]
__all__ = ["get_current_open_milestone", "all_milestones_paid"]
