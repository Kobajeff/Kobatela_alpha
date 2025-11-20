"""KCT Public Sector Lite API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.escrow import EscrowAgreement
from app.models.gov_public import GovProject, GovProjectManager, GovProjectMandate
from app.models.user import User
from app.schemas.kct_public import (
    GovProjectCreate,
    GovProjectMandateCreate,
    GovProjectManagerCreate,
    GovProjectRead,
)
from app.security import ApiScope, require_public_user, require_scope
from app.services.kct_public import compute_project_stats, get_project, merge_project_and_stats
from app.utils.errors import error_response

router = APIRouter(
    prefix="/kct_public",
    tags=["kct_public"],
    dependencies=[Depends(require_scope({ApiScope.sender, ApiScope.admin})), Depends(require_public_user)],
)


@router.post(
    "/projects",
    response_model=GovProjectRead,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    payload: GovProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_public_user),
):
    project = GovProject(
        label=payload.label,
        project_type=payload.project_type,
        country=payload.country,
        city=payload.city,
        domain=payload.domain.value,
        gov_entity_id=payload.gov_entity_id,
        execution_mode="basic",
        status="active",
    )
    db.add(project)
    db.flush()

    manager = GovProjectManager(
        gov_project_id=project.id,
        user_id=current_user.id,
        role="project_manager",
        is_primary=True,
    )
    db.add(manager)
    db.commit()
    db.refresh(project)

    stats = compute_project_stats(db, project.id)
    return merge_project_and_stats(project, stats)


@router.post(
    "/projects/{project_id}/managers",
    status_code=status.HTTP_201_CREATED,
)
def add_project_manager(
    project_id: int,
    payload: GovProjectManagerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_public_user),
):
    project = get_project(db, project_id, current_user)

    manager = GovProjectManager(
        gov_project_id=project.id,
        user_id=payload.user_id,
        role=payload.role,
        is_primary=payload.is_primary or False,
    )
    db.add(manager)
    db.commit()
    return {"status": "added"}


@router.post(
    "/projects/{project_id}/mandates",
    status_code=status.HTTP_201_CREATED,
)
def attach_project_mandate(
    project_id: int,
    payload: GovProjectMandateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_public_user),
):
    project = get_project(db, project_id, current_user)

    escrow = db.get(EscrowAgreement, payload.escrow_id)
    if not escrow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("NOT_FOUND", "Escrow not found."),
        )

    if escrow.domain != project.domain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(
                "DOMAIN_MISMATCH", "Escrow domain must match project domain.",
            ),
        )

    mandate = GovProjectMandate(
        gov_project_id=project.id,
        escrow_id=escrow.id,
    )
    db.add(mandate)
    db.commit()
    return {"status": "attached"}


@router.get("/projects/{project_id}", response_model=GovProjectRead)
def get_project_view(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_public_user),
):
    project = get_project(db, project_id, current_user)
    stats = compute_project_stats(db, project.id)
    return merge_project_and_stats(project, stats)


@router.get("/projects", response_model=list[GovProjectRead])
def list_projects(
    domain: str | None = Query(None),
    country: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_public_user),
):
    _ = current_user  # satisfies dependency while allowing future manager checks
    stmt = select(GovProject).where(GovProject.domain.in_(["public", "aid"]))

    if domain:
        stmt = stmt.where(GovProject.domain == domain)
    if country:
        stmt = stmt.where(GovProject.country == country)
    if status_filter:
        stmt = stmt.where(GovProject.status == status_filter)

    projects = db.scalars(stmt).all()

    results: list[GovProjectRead] = []
    for project in projects:
        stats = compute_project_stats(db, project.id)
        results.append(merge_project_and_stats(project, stats))
    return results
