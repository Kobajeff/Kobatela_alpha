"""User endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserRead
from app.models.api_key import ApiKey, ApiScope
from app.security import require_scope
from app.utils.audit import actor_from_api_key, log_audit
from app.utils.errors import error_response

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_scope({ApiScope.admin, ApiScope.support})),
) -> User:
    """Create a new user."""

    user = User(**payload.model_dump())
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response("USER_CREATE_FAILED", "Could not create user."),
        ) from exc

    actor = actor_from_api_key(api_key, fallback="apikey:unknown")
    log_audit(
        db,
        actor=actor,
        action="CREATE_USER",
        entity="User",
        entity_id=user.id,
        data={"username": user.username, "email": user.email},
    )

    db.commit()
    db.refresh(user)
    return user


@router.get(
    "/{user_id}",
    response_model=UserRead,
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _api_key: ApiKey = Depends(require_scope({ApiScope.admin, ApiScope.support})),
) -> User:
    """Retrieve a user by identifier."""

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_response("USER_NOT_FOUND", "User not found."))
    return user
