"""Services for KCT Public Sector operations."""
from decimal import Decimal
from typing import Any, Dict

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.escrow import EscrowAgreement
from app.models.gov_public import GovProject, GovProjectMandate, GovProjectManager
from app.models.milestone import Milestone, MilestoneStatus
from app.models.payment import Payment, PaymentStatus
from app.models.user import User
from app.utils.errors import error_response


def get_project(db: Session, project_id: int, current_user: User) -> GovProject:
    """Fetch a project and enforce public user access."""

    project = db.get(GovProject, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("NOT_FOUND", "Project not found."),
        )

    if current_user.public_tag not in {"GOV", "ONG"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response("FORBIDDEN", "Not a public user."),
        )

    is_manager = db.scalar(
        select(GovProjectManager.id).where(
            GovProjectManager.gov_project_id == project.id,
            GovProjectManager.user_id == current_user.id,
        )
    )
    if not is_manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response(
                "FORBIDDEN",
                "User is not assigned to this public project.",
            ),
        )

    return project


def compute_project_stats(db: Session, project_id: int) -> Dict[str, Any]:
    """Compute aggregated escrow/payment statistics for a project."""

    escrow_ids = db.scalars(
        select(GovProjectMandate.escrow_id).where(
            GovProjectMandate.gov_project_id == project_id
        )
    ).all()

    if not escrow_ids:
        return {
            "total_amount": Decimal("0"),
            "released_amount": Decimal("0"),
            "remaining_amount": Decimal("0"),
            "current_milestone": None,
        }

    total = db.scalars(
        select(func.coalesce(func.sum(EscrowAgreement.amount_total), 0)).where(
            EscrowAgreement.id.in_(escrow_ids)
        )
    ).one()

    released = db.scalars(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.escrow_id.in_(escrow_ids),
            Payment.status == PaymentStatus.SETTLED,
        )
    ).one()

    remaining = total - released

    current_milestone = db.scalars(
        select(func.max(Milestone.idx)).where(
            Milestone.escrow_id.in_(escrow_ids),
            Milestone.status.in_([MilestoneStatus.PAID, MilestoneStatus.PAYING]),
        )
    ).one()

    return {
        "total_amount": total,
        "released_amount": released,
        "remaining_amount": remaining,
        "current_milestone": current_milestone,
    }


def merge_project_and_stats(project: GovProject, stats: Dict[str, Any]) -> Dict[str, Any]:
    """Combine project data with precomputed stats for serialization."""

    return {
        "id": project.id,
        "label": project.label,
        "project_type": project.project_type,
        "country": project.country,
        "city": project.city,
        "domain": project.domain,
        "status": project.status,
        "total_amount": stats["total_amount"],
        "released_amount": stats["released_amount"],
        "remaining_amount": stats["remaining_amount"],
        "current_milestone": stats["current_milestone"],
    }
