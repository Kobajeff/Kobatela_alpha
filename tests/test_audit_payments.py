from decimal import Decimal
from uuid import uuid4

from app.models import AuditLog, EscrowAgreement, EscrowDeposit, EscrowStatus, PaymentStatus, User
from app.services import payments as payments_service
from app.utils.time import utcnow


def test_payment_execution_is_audited(db_session):
    client_user = User(username=f"client-{uuid4().hex[:8]}", email=f"c-{uuid4().hex[:6]}@example.com")
    provider_user = User(username=f"provider-{uuid4().hex[:8]}", email=f"p-{uuid4().hex[:6]}@example.com")
    db_session.add_all([client_user, provider_user])
    db_session.flush()

    escrow = EscrowAgreement(
        client_id=client_user.id,
        provider_id=provider_user.id,
        amount_total=Decimal("200.00"),
        currency="USD",
        status=EscrowStatus.FUNDED,
        release_conditions_json={},
        deadline_at=utcnow(),
    )
    db_session.add(escrow)
    db_session.flush()

    deposit = EscrowDeposit(escrow_id=escrow.id, amount=Decimal("200.00"), idempotency_key=f"dep-{uuid4().hex[:6]}")
    db_session.add(deposit)
    db_session.commit()

    payment = payments_service.execute_payout(
        db_session,
        escrow=escrow,
        milestone=None,
        amount=Decimal("50.00"),
        idempotency_key="audit-pay-1",
    )

    db_session.refresh(payment)
    assert payment.status in {PaymentStatus.SENT, PaymentStatus.SETTLED}

    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.entity == "Payment",
            AuditLog.entity_id == payment.id,
            AuditLog.action == "PAYMENT_EXECUTED",
        )
        .one_or_none()
    )
    assert audit is not None
    assert audit.data_json.get("amount") == str(payment.amount)
