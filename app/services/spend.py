"""Spend management services."""
import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy import and_, case, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.spend import AllowedUsage, Merchant, Purchase, PurchaseStatus, SpendCategory
from app.models.usage_mandate import UsageMandate, UsageMandateStatus
from app.schemas.spend import (
    AllowedUsageCreate,
    MerchantCreate,
    PurchaseCreate,
    SpendCategoryCreate,
)
from app.services.mandates import audit_mandate_event
from app.services.idempotency import get_existing_by_key
from app.utils.audit import log_audit
from app.utils.errors import error_response
from app.utils.time import utcnow

_DECIMAL_QUANT = Decimal("0.01")


def _to_decimal(amount: Decimal | float | int | str) -> Decimal:
    """Normalize amount inputs to two-decimal ``Decimal`` values."""

    if isinstance(amount, Decimal):
        value = amount
    else:
        value = Decimal(str(amount))
    return value.quantize(_DECIMAL_QUANT, rounding=ROUND_HALF_UP)

logger = logging.getLogger(__name__)


def _resolve_beneficiary(payload: PurchaseCreate) -> int:
    """Return the beneficiary performing the spend."""

    return payload.beneficiary_id or payload.sender_id


def _find_active_mandate_for_purchase(
    db: Session,
    *,
    sender_id: int,
    beneficiary_id: int,
    currency: str,
    now: datetime,
) -> UsageMandate | None:
    stmt = (
        select(UsageMandate)
        .where(
            and_(
                UsageMandate.sender_id == sender_id,
                UsageMandate.beneficiary_id == beneficiary_id,
                UsageMandate.currency == currency,
                UsageMandate.status == UsageMandateStatus.ACTIVE,
                UsageMandate.expires_at > now,
            )
        )
        .order_by(UsageMandate.expires_at.asc(), UsageMandate.id.asc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _consume_mandate_atomic(
    db: Session,
    *,
    mandate: UsageMandate,
    sender_id: int,
    beneficiary_id: int,
    currency: str,
    amount: Decimal,
    now: datetime,
) -> bool:
    new_total = UsageMandate.total_spent + amount
    stmt = (
        update(UsageMandate)
        .where(
            and_(
                UsageMandate.id == mandate.id,
                UsageMandate.sender_id == sender_id,
                UsageMandate.beneficiary_id == beneficiary_id,
                UsageMandate.currency == currency,
                UsageMandate.status == UsageMandateStatus.ACTIVE,
                UsageMandate.expires_at > now,
                new_total <= UsageMandate.total_amount,
            )
        )
        .values(
            total_spent=new_total,
            status=case(
                (new_total >= UsageMandate.total_amount, UsageMandateStatus.CONSUMED),
                else_=UsageMandateStatus.ACTIVE,
            ),
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    result = db.execute(stmt)
    return result.rowcount == 1


def create_category(
    db: Session, payload: SpendCategoryCreate, *, actor: str | None = None
) -> SpendCategory:
    """Create a new spend category."""

    category = SpendCategory(code=payload.code, label=payload.label)
    db.add(category)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response("CATEGORY_EXISTS", "Spend category already exists."),
        )

    log_audit(
        db,
        actor=actor or "admin",
        action="SPEND_CATEGORY_CREATED",
        entity="SpendCategory",
        entity_id=category.id,
        data={"code": category.code, "label": category.label},
    )

    db.commit()
    db.refresh(category)
    logger.info("Spend category created", extra={"category_id": category.id, "code": category.code})
    return category


def create_merchant(
    db: Session, payload: MerchantCreate, *, actor: str | None = None
) -> Merchant:
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
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response("MERCHANT_EXISTS", "Merchant already exists."),
        )

    log_audit(
        db,
        actor=actor or "admin",
        action="SPEND_MERCHANT_CREATED",
        entity="Merchant",
        entity_id=merchant.id,
        data={
            "name": merchant.name,
            "category_id": merchant.category_id,
            "is_certified": merchant.is_certified,
        },
    )

    db.commit()
    db.refresh(merchant)
    logger.info("Merchant created", extra={"merchant_id": merchant.id})
    return merchant


def allow_usage(
    db: Session, payload: AllowedUsageCreate, *, actor: str | None = None
) -> dict[str, str]:
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
        db.flush()
    except IntegrityError:
        db.rollback()
        logger.info("Usage already allowed", extra={"owner_id": payload.owner_id})
        return {"status": "exists"}

    log_audit(
        db,
        actor=actor or "admin",
        action="SPEND_ALLOW_CREATED",
        entity="AllowedUsage",
        entity_id=usage.id,
        data={
            "owner_id": payload.owner_id,
            "merchant_id": payload.merchant_id,
            "category_id": payload.category_id,
        },
    )

    db.commit()
    logger.info("Usage allowed", extra={"owner_id": payload.owner_id})
    return {"status": "added"}


def create_purchase(
    db: Session,
    payload: PurchaseCreate,
    *,
    idempotency_key: str | None,
    actor: str | None = None,
) -> Purchase:
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

    beneficiary_id = _resolve_beneficiary(payload)
    category_id = payload.category_id or merchant.category_id

    now = utcnow()
    mandate = _find_active_mandate_for_purchase(
        db,
        sender_id=payload.sender_id,
        beneficiary_id=beneficiary_id,
        currency=payload.currency,
        now=now,
    )

    if mandate is None:
        logger.warning(
            "Unauthorized purchase: no active mandate",
            extra={
                "sender_id": payload.sender_id,
                "beneficiary_id": beneficiary_id,
                "merchant_id": merchant.id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response("MANDATE_REQUIRED", "No active usage mandate for beneficiary."),
        )

    if mandate.allowed_merchant_id is not None and mandate.allowed_merchant_id != merchant.id:
        logger.warning(
            "Unauthorized purchase: merchant forbidden by mandate",
            extra={
                "mandate_id": mandate.id,
                "beneficiary_id": beneficiary_id,
                "merchant_id": merchant.id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response("MANDATE_MERCHANT_FORBIDDEN", "Merchant not allowed for this mandate."),
        )

    if mandate.allowed_category_id is not None and mandate.allowed_category_id != category_id:
        logger.warning(
            "Unauthorized purchase: category forbidden by mandate",
            extra={
                "mandate_id": mandate.id,
                "beneficiary_id": beneficiary_id,
                "category_id": category_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response("MANDATE_CATEGORY_FORBIDDEN", "Category not allowed for this mandate."),
        )

    allowed = False
    direct_stmt = select(AllowedUsage).where(
        AllowedUsage.owner_id == beneficiary_id,
        AllowedUsage.merchant_id == merchant.id,
    )
    if db.execute(direct_stmt).first():
        allowed = True
    elif category_id is not None:
        category_stmt = select(AllowedUsage).where(
            AllowedUsage.owner_id == beneficiary_id,
            AllowedUsage.category_id == category_id,
        )
        if db.execute(category_stmt).first():
            allowed = True

    if not allowed and not merchant.is_certified:
        logger.warning(
            "Unauthorized usage attempt",
            extra={
                "sender_id": payload.sender_id,
                "beneficiary_id": beneficiary_id,
                "merchant_id": payload.merchant_id,
                "category_id": category_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response("UNAUTHORIZED_USAGE", "Sender is not authorized for this purchase."),
        )

    amount = _to_decimal(payload.amount)
    consumed = _consume_mandate_atomic(
        db,
        mandate=mandate,
        sender_id=payload.sender_id,
        beneficiary_id=beneficiary_id,
        currency=payload.currency,
        amount=amount,
        now=now,
    )
    if not consumed:
        logger.warning(
            "Mandate consumption failed",
            extra={
                "mandate_id": mandate.id,
                "sender_id": payload.sender_id,
                "beneficiary_id": beneficiary_id,
                "attempt_amount": str(amount),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response(
                "MANDATE_CONFLICT",
                "Mandate limit exceeded or concurrent spend detected.",
            ),
        )

    db.refresh(mandate)

    purchase = Purchase(
        sender_id=beneficiary_id,
        merchant_id=merchant.id,
        category_id=category_id,
        amount=amount,
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

    audit_mandate_event(
        db,
        actor=f"beneficiary:{beneficiary_id}",
        action="MANDATE_CONSUMED",
        mandate_id=mandate.id,
        data={
            "amount": str(amount),
            "currency": payload.currency,
            "purchase_id": purchase.id,
            "total_spent": str(mandate.total_spent),
            "total_amount": str(mandate.total_amount),
        },
    )

    audit = AuditLog(
        actor=actor or "system",
        action="CREATE_PURCHASE",
        entity="Purchase",
        entity_id=purchase.id,
        data_json={
            **payload.model_dump(mode="json"),
            "resolved_beneficiary_id": beneficiary_id,
        },
        at=utcnow(),
    )
    db.add(audit)

    db.commit()
    db.refresh(purchase)
    logger.info("Purchase completed", extra={"purchase_id": purchase.id})
    return purchase
