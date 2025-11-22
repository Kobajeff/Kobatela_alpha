"""User endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.user import User
from app.models.api_key import ApiKey, ApiScope
from app.schemas.user import StripeAccountLinkRead, UserCreate, UserRead
from app.services.psp_stripe import StripeClient
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
    api_key: ApiKey = Depends(require_scope({ApiScope.admin, ApiScope.support})),
) -> User:
    """Retrieve a user by identifier."""

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_response("USER_NOT_FOUND", "User not found."))

    actor = actor_from_api_key(api_key, fallback="apikey:unknown")
    log_audit(
        db,
        actor=actor,
        action="READ_USER",
        entity="User",
        entity_id=user.id,
        data={"reason": "api_read"},
    )

    return user


@router.post(
    "/{user_id}/psp/stripe/account-link",
    response_model=StripeAccountLinkRead,
    status_code=status.HTTP_201_CREATED,
)
def create_stripe_account_link_for_user(
    user_id: int,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_scope({ApiScope.admin})),
):
    """Create a Stripe Connect onboarding link for the given user."""

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("USER_NOT_FOUND", "User not found."),
        )

    settings = get_settings()
    if not (settings.STRIPE_ENABLED and settings.STRIPE_CONNECT_ENABLED):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_response("STRIPE_CONNECT_DISABLED", "Stripe Connect is disabled."),
        )

    stripe_client = StripeClient(settings)

    if not user.stripe_account_id:
        account = stripe_client.create_connected_account(user)
        user.stripe_account_id = account.id
        user.stripe_payout_status = "pending_onboarding"
        db.add(user)
        db.commit()
        db.refresh(user)

    link = stripe_client.create_account_link(user.stripe_account_id)
    return StripeAccountLinkRead(url=link.url)
