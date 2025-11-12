"""User endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_

from app.db import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserRead
from app.security import require_api_key
from app.utils.errors import error_response

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_api_key)])


def _find_existing_user(db: Session, *, username: str, email: str) -> User | None:
    return (
        db.query(User)
        .filter((User.username == username) | (User.email == email))
        .one_or_none()
    )


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, response: Response, db: Session = Depends(get_db)) -> User:
    """
    Create a new user (idempotent).
    - 201 Created si nouveau
    - 200 OK si (username OR email) existe déjà → retourne l'existant
    """
    # Idempotence optimiste
    existing = _find_existing_user(db, username=payload.username, email=payload.email)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return existing

    # Création
    user = User(**payload.model_dump())
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError:
        # Course: quelqu'un l'a créé juste avant le commit
        db.rollback()
        existing = _find_existing_user(db, username=payload.username, email=payload.email)
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            return existing
        # Cas réellement conflictuel (très rare) : renvoyer 409
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("USER_CONFLICT", "Username/email already in use."),
        )


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, db: Session = Depends(get_db)) -> User:
    """Retrieve a user by identifier."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("USER_NOT_FOUND", "User not found."),
        )
    return user
