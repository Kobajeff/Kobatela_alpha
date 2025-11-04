"""Spend management services."""
import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.spend import AllowedUsage, Merchant, Purchase, PurchaseStatus, SpendCategory
from app.schemas.spend import (
    AllowedUsageCreate,
    MerchantCreate,
    PurchaseCreate,
    SpendCategoryCreate,
)
from app.services.idempotency import get_existing_by_key
from app.utils.errors import error_response
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


def create_category(db: Session, payload: SpendCategoryCreate) -> SpendCategory:
    """Create a new spend category."""

    category = SpendCategory(code=payload.code, label=payload.label)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response("CATEGORY_EXISTS", "Spend category already exists."),
        )
    db.refresh(category)
    logger.info("Spend category created", extra={"category_id": category.id, "code": category.code})
    return category


def create_merchant(db: Session, payload: MerchantCreate) -> Merchant:
    """Create a merchant."""

    category = None
    if payload.category_id is not None:
        category = db.get(SpendCategory, payload.category_id)
        if category is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("CATEGORY_NOT_FOUND", "Spend category not found."),
            )

    merchant = Merchant(name=payload.name, category=category, is_certified=payload.is_certified)
    db.add(merchant)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response("MERCHANT_EXISTS", "Merchant already exists."),
        )
    db.refresh(merchant)
    logger.info("Merchant created", extra={"merchant_id": merchant.id})
    return merchant


def allow_usage(db: Session, payload: AllowedUsageCreate) -> dict[str, str]:
    """Allow usage for a merchant or category."""

    has_merchant = payload.merchant_id is not None
    has_category = payload.category_id is not None
    if has_merchant == has_category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(
                "INVALID_USAGE_RULE",
                "Exactly one of merchant_id or category_id must be provided.",
            ),
        )

    if payload.merchant_id is not None:
        merchant = db.get(Merchant, payload.merchant_id)
        if merchant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("MERCHANT_NOT_FOUND", "Merchant not found."),
            )
    if payload.category_id is not None:
        category = db.get(SpendCategory, payload.category_id)
        if category is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("CATEGORY_NOT_FOUND", "Spend category not found."),
            )

    usage = AllowedUsage(
        owner_id=payload.owner_id,
        merchant_id=payload.merchant_id,
        category_id=payload.category_id,
    )
    db.add(usage)
    try:
        db.commit()
        logger.info("Usage allowed", extra={"owner_id": payload.owner_id})
        return {"status": "added"}
    except IntegrityError:
        db.rollback()
        logger.info("Usage already allowed", extra={"owner_id": payload.owner_id})
        return {"status": "exists"}


def create_purchase(db: Session, payload: PurchaseCreate, *, idempotency_key: str | None) -> Purchase:
    """Create an authorized purchase if the usage is allowed."""

    if idempotency_key:
        existing = get_existing_by_key(db, Purchase, idempotency_key)
        if existing:
            logger.info("Idempotent purchase reused", extra={"purchase_id": existing.id})
            return existing

    merchant = db.get(Merchant, payload.merchant_id)
    if merchant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("MERCHANT_NOT_FOUND", "Merchant not found."),
        )

    category_id = payload.category_id or merchant.category_id

    allowed = False
    direct_stmt = select(AllowedUsage).where(
        AllowedUsage.owner_id == payload.sender_id,
        AllowedUsage.merchant_id == merchant.id,
    )
    if db.execute(direct_stmt).first():
        allowed = True
    elif category_id is not None:
        category_stmt = select(AllowedUsage).where(
            AllowedUsage.owner_id == payload.sender_id,
            AllowedUsage.category_id == category_id,
        )
        if db.execute(category_stmt).first():
            allowed = True

    if not allowed and not merchant.is_certified:
        logger.warning(
            "Unauthorized usage attempt",
            extra={
                "sender_id": payload.sender_id,
                "merchant_id": payload.merchant_id,
                "category_id": category_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response("UNAUTHORIZED_USAGE", "Sender is not authorized for this purchase."),
        )

    purchase = Purchase(
        sender_id=payload.sender_id,
        merchant_id=merchant.id,
        category_id=category_id,
        amount=payload.amount,
        currency=payload.currency,
        status=PurchaseStatus.COMPLETED,
        idempotency_key=idempotency_key,
    )
    db.add(purchase)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            existing = get_existing_by_key(db, Purchase, idempotency_key)
            if existing:
                logger.info(
                    "Idempotent purchase reused after race",
                    extra={"purchase_id": existing.id},
                )
                return existing
        raise

    audit = AuditLog(
        actor="system",
        action="CREATE_PURCHASE",
        entity="Purchase",
        entity_id=purchase.id,
        data_json=payload.model_dump(),
        at=utcnow(),
    )
    db.add(audit)

    db.commit()
    db.refresh(purchase)
    logger.info("Purchase completed", extra={"purchase_id": purchase.id})
    return purchase
