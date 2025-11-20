import pytest


def test_ai_proof_advisor_logs_status(monkeypatch):
    from app.services import ai_proof_advisor

    monkeypatch.setattr(ai_proof_advisor, "ai_enabled", lambda: False)

    result = ai_proof_advisor.call_ai_proof_advisor(
        context={"document_context": {"metadata": {}}},
        proof_storage_url=None,
    )

    assert result["risk_level"] == "warning"
    assert "ai_disabled" in result.get("flags", [])


def test_invoice_ocr_logs_status(monkeypatch):
    from app.services import invoice_ocr

    class DummySettings:
        INVOICE_OCR_PROVIDER = "none"

    monkeypatch.setattr(invoice_ocr, "_current_settings", lambda: DummySettings())
    monkeypatch.setattr(invoice_ocr, "invoice_ocr_enabled", lambda: False)

    metadata = invoice_ocr.enrich_metadata_with_invoice_ocr(
        storage_url="test://file.pdf", existing_metadata={}
    )

    assert metadata["ocr_status"] == "disabled"
    assert metadata["ocr_provider"] == "none"


def test_ai_circuit_breaker_skips_when_open(monkeypatch):
    from app.services import ai_proof_advisor

    ai_proof_advisor._AI_CIRCUIT_OPEN = True
    ai_proof_advisor._AI_FAILURES = 5

    result = ai_proof_advisor.call_ai_proof_advisor(
        context={"document_context": {"metadata": {}}}, proof_storage_url=None
    )

    assert "circuit_breaker_open" in result.get("flags", [])
    assert result["score"] == 0.5

    ai_proof_advisor._AI_CIRCUIT_OPEN = False
    ai_proof_advisor._AI_FAILURES = 0


def test_ai_circuit_breaker_opens_after_failures(monkeypatch):
    from app.services import ai_proof_advisor

    class DummySettings:
        OPENAI_API_KEY = "test"

    class FailingClient:
        def __init__(self, *_args, **_kwargs):
            self.responses = self

        def create(self, *_args, **_kwargs):
            raise ValueError("boom")

    ai_proof_advisor._AI_FAILURES = 4
    ai_proof_advisor._AI_CIRCUIT_OPEN = False

    monkeypatch.setattr(ai_proof_advisor, "get_settings", lambda: DummySettings())
    monkeypatch.setattr(ai_proof_advisor, "ai_enabled", lambda: True)
    monkeypatch.setattr(ai_proof_advisor, "ai_model", lambda: "model")
    monkeypatch.setattr(ai_proof_advisor, "ai_timeout_seconds", lambda: 1)
    monkeypatch.setattr(ai_proof_advisor, "OpenAI", FailingClient)

    result = ai_proof_advisor.call_ai_proof_advisor(
        context={"document_context": {"metadata": {}}}, proof_storage_url=None
    )

    assert ai_proof_advisor._AI_CIRCUIT_OPEN is True
    assert "exception_during_call" in result.get("flags", [])

    ai_proof_advisor._AI_FAILURES = 0
    ai_proof_advisor._AI_CIRCUIT_OPEN = False
