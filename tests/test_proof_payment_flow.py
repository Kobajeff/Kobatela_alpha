"""End-to-end test for proof approval and payment execution."""
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from sqlalchemy import select

from app.config import get_settings
from app.models import (
    EscrowAgreement,
    EscrowStatus,
    Milestone,
    MilestoneStatus,
    Payment,
    PaymentStatus,
    User,
)
from app.schemas.proof import ProofCreate
from app.services import proofs as proofs_service


def _create_pdf_milestone(db_session):
    """Create a simple escrow + PDF milestone for proof submissions."""

    client = User(
        username=f"client-{uuid4().hex[:8]}",
        email=f"client-{uuid4().hex[:8]}@example.com",
    )
    provider = User(
        username=f"provider-{uuid4().hex[:8]}",
        email=f"provider-{uuid4().hex[:8]}@example.com",
    )
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


@pytest.mark.anyio("asyncio")
async def test_proof_approval_triggers_payment(client, auth_headers, db_session):
    client_resp = await client.post(
        "/users",
        json={"username": "escrow-client", "email": "escrow-client@example.com"},
        headers=auth_headers,
    )
    provider_resp = await client.post(
        "/users",
        json={"username": "escrow-provider", "email": "escrow-provider@example.com"},
        headers=auth_headers,
    )
    assert client_resp.status_code == 201
    assert provider_resp.status_code == 201
    client_id = client_resp.json()["id"]
    provider_id = provider_resp.json()["id"]

    escrow_resp = await client.post(
        "/escrows",
        json={
            "client_id": client_id,
            "provider_id": provider_id,
            "amount_total": 500.0,
            "currency": "USD",
            "release_conditions": {"type": "milestone"},
            "deadline_at": datetime.now(tz=UTC).isoformat(),
        },
        headers=auth_headers,
    )
    assert escrow_resp.status_code == 201
    escrow_id = escrow_resp.json()["id"]

    milestone = Milestone(
        escrow_id=escrow_id,
        idx=1,
        label="Prototype delivery",
        amount=Decimal("500.00"),
        proof_type="PHOTO",
        validator="SENDER",
    )
    db_session.add(milestone)
    db_session.flush()

    deposit_headers = {**auth_headers, "Idempotency-Key": "proof-flow-deposit"}
    deposit_resp = await client.post(
        f"/escrows/{escrow_id}/deposit",
        json={"amount": 500.0},
        headers=deposit_headers,
    )
    assert deposit_resp.status_code == 200

    proof_resp = await client.post(
        "/proofs",
        json={
            "escrow_id": escrow_id,
            "milestone_idx": 1,
            "type": "PHOTO",
            "storage_url": "https://example.com/proof.jpg",
            "sha256": "abc123",
        },
        headers=auth_headers,
    )
    assert proof_resp.status_code == 201
    proof_id = proof_resp.json()["id"]

    db_session.refresh(milestone)
    assert milestone.status == MilestoneStatus.PENDING_REVIEW

    decision_resp = await client.post(
        f"/proofs/{proof_id}/decision",
        json={"decision": "approved", "note": "Looks good"},
        headers=auth_headers,
    )
    assert decision_resp.status_code == 200
    assert decision_resp.json()["status"] == "APPROVED"

    db_session.refresh(milestone)
    assert milestone.status == MilestoneStatus.PAID

    payment = db_session.scalars(select(Payment).where(Payment.milestone_id == milestone.id)).one()
    assert payment.status == PaymentStatus.SENT

    escrow = db_session.get(EscrowAgreement, escrow_id)
    assert escrow is not None
    db_session.refresh(escrow)
    assert escrow.status == EscrowStatus.RELEASED

    second_exec = await client.post(f"/payments/execute/{payment.id}", headers=auth_headers)
    assert second_exec.status_code == 200
    assert second_exec.json()["status"] == "SENT"


def test_submit_proof_persists_ai_columns(monkeypatch, db_session):
    settings = get_settings()
    original_flag = settings.AI_PROOF_ADVISOR_ENABLED
    settings.AI_PROOF_ADVISOR_ENABLED = True
    stub_result = {
        "risk_level": "warning",
        "score": 0.66,
        "flags": ["invoice_amount_match"],
        "explanation": "Analyse réussie",
    }
    monkeypatch.setattr(
        proofs_service, "call_ai_proof_advisor", lambda **_: stub_result,
    )
    try:
        client = User(username="ai-client", email="ai-client@example.com")
        provider = User(username="ai-provider", email="ai-provider@example.com")
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
            label="Document",
            amount=Decimal("25.00"),
            proof_type="PDF",
            validator="SENDER",
            status=MilestoneStatus.WAITING,
        )
        db_session.add(milestone)
        db_session.commit()

        payload = ProofCreate(
            escrow_id=escrow.id,
            milestone_idx=1,
            type="PDF",
            storage_url="https://storage.example.com/proofs/doc.pdf",
            sha256="hash-ai-proof",
            metadata={"invoice_total_amount": 25},
        )

        proof = proofs_service.submit_proof(db_session, payload, actor="apikey:test")
        db_session.refresh(proof)

        assert proof.ai_risk_level == stub_result["risk_level"]
        assert isinstance(proof.ai_score, Decimal)
        assert proof.ai_score == Decimal("0.66")
        assert proof.ai_flags == stub_result["flags"]
        assert proof.ai_explanation == stub_result["explanation"]
        assert proof.ai_checked_at is not None
        assert proof.metadata_["ai_assessment"] == stub_result
    finally:
        settings.AI_PROOF_ADVISOR_ENABLED = original_flag


def test_submit_proof_uses_ocr_invoice_fields(monkeypatch, db_session):
    escrow, milestone = _create_pdf_milestone(db_session)

    def fake_enrich(*, storage_url: str, existing_metadata: dict | None):
        enriched = dict(existing_metadata or {})
        enriched.setdefault("invoice_total_amount", Decimal("321.00"))
        enriched.setdefault("invoice_currency", "eur")
        return enriched

    monkeypatch.setattr(
        proofs_service,
        "enrich_metadata_with_invoice_ocr",
        fake_enrich,
    )

    payload = ProofCreate(
        escrow_id=escrow.id,
        milestone_idx=1,
        type="PDF",
        storage_url="https://storage.example.com/proofs/doc.pdf",
        sha256="hash-invoice-proof",
        metadata={},
    )

    proof = proofs_service.submit_proof(db_session, payload, actor="apikey:test")
    db_session.refresh(proof)

    assert proof.invoice_total_amount == Decimal("321.00")
    assert proof.invoice_currency == "EUR"
    assert proof.metadata_["invoice_total_amount"] == "321.00"
    assert proof.metadata_["invoice_currency"] == "eur"


def test_submit_proof_prefers_user_invoice_fields(monkeypatch, db_session):
    escrow, milestone = _create_pdf_milestone(db_session)

    def fake_enrich(*, storage_url: str, existing_metadata: dict | None):
        enriched = dict(existing_metadata or {})
        enriched.setdefault("ocr", {})["invoice_total_amount"] = Decimal("999.99")
        enriched.setdefault("ocr", {})["invoice_currency"] = "eur"
        return enriched

    monkeypatch.setattr(
        proofs_service,
        "enrich_metadata_with_invoice_ocr",
        fake_enrich,
    )

    payload = ProofCreate(
        escrow_id=escrow.id,
        milestone_idx=1,
        type="PDF",
        storage_url="https://storage.example.com/proofs/doc.pdf",
        sha256="hash-invoice-proof-user",
        metadata={"invoice_total_amount": "150.50", "invoice_currency": "gbp"},
    )

    proof = proofs_service.submit_proof(db_session, payload, actor="apikey:test")
    db_session.refresh(proof)

    assert proof.invoice_total_amount == Decimal("150.50")
    assert proof.invoice_currency == "GBP"
    assert proof.metadata_["invoice_total_amount"] == "150.50"
    assert proof.metadata_["invoice_currency"] == "gbp"
    assert proof.metadata_["ocr"]["invoice_total_amount"] == "999.99"
    assert proof.metadata_["ocr"]["invoice_currency"] == "eur"


def test_submit_proof_invalid_currency_returns_422(monkeypatch, db_session):
    escrow, milestone = _create_pdf_milestone(db_session)

    def fake_enrich(*, storage_url: str, existing_metadata: dict | None):
        enriched = dict(existing_metadata or {})
        enriched.setdefault("invoice_currency", "usd4")
        return enriched

    monkeypatch.setattr(
        proofs_service,
        "enrich_metadata_with_invoice_ocr",
        fake_enrich,
    )

    payload = ProofCreate(
        escrow_id=escrow.id,
        milestone_idx=1,
        type="PDF",
        storage_url="https://storage.example.com/proofs/doc.pdf",
        sha256="hash-invoice-proof-invalid-currency",
        metadata={},
    )

    with pytest.raises(HTTPException) as exc:
        proofs_service.submit_proof(db_session, payload, actor="apikey:test")

    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc.value.detail["error"]["code"] == "INVOICE_NORMALIZATION_ERROR"
