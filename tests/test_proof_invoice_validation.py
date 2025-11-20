from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.schemas.proof import ProofCreate
from app.services import proofs as proofs_service


def _setup_pdf_escrow(db_session):
    from decimal import Decimal
    from datetime import datetime, UTC
    from app.models import EscrowAgreement, EscrowStatus, Milestone, MilestoneStatus, User

    client = User(username="invoice-client", email="invoice-client@example.com")
    provider = User(username="invoice-provider", email="invoice-provider@example.com")
    db_session.add_all([client, provider])
    db_session.flush()

    escrow = EscrowAgreement(
        client_id=client.id,
        provider_id=provider.id,
        amount_total=Decimal("100.00"),
        currency="USD",
        status=EscrowStatus.FUNDED,
        release_conditions_json={"type": "milestone"},
        deadline_at=datetime.now(tz=UTC),
    )
    db_session.add(escrow)
    db_session.flush()

    milestone = Milestone(
        escrow_id=escrow.id,
        idx=1,
        label="Invoice",
        amount=Decimal("25.00"),
        proof_type="PDF",
        validator="SENDER",
        status=MilestoneStatus.WAITING,
    )
    db_session.add(milestone)
    db_session.commit()
    return escrow, milestone


def test_submit_proof_rejects_invalid_invoice_currency(db_session):
    escrow, milestone = _setup_pdf_escrow(db_session)

    payload = ProofCreate(
        escrow_id=escrow.id,
        milestone_idx=1,
        type="PDF",
        storage_url="https://example.com/invoice.pdf",
        sha256="sha",
        metadata={"invoice_total_amount": "99.99", "invoice_currency": "usd4"},
    )

    with pytest.raises(HTTPException) as excinfo:
        proofs_service.submit_proof(db_session, payload, actor="tester")

    assert excinfo.value.status_code == 422
    assert excinfo.value.detail["error"]["code"] == "INVOICE_NORMALIZATION_ERROR"


def test_submit_proof_accepts_valid_invoice_metadata(db_session):
    escrow, milestone = _setup_pdf_escrow(db_session)

    payload = ProofCreate(
        escrow_id=escrow.id,
        milestone_idx=1,
        type="PDF",
        storage_url="https://example.com/invoice-ok.pdf",
        sha256="sha256-ok",
        metadata={"invoice_total_amount": "150.50", "invoice_currency": "eur"},
    )

    proof = proofs_service.submit_proof(db_session, payload, actor="tester")

    assert proof.invoice_total_amount == Decimal("150.50")
    assert proof.invoice_currency == "EUR"
