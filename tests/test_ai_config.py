"""Tests for AI Proof Advisor configuration defaults."""


def test_ai_proof_disabled_by_default():
    from app.config import settings

    # AI Proof Advisor must be disabled by default for safety
    assert settings.AI_PROOF_ADVISOR_ENABLED is False


def test_call_ai_proof_advisor_returns_fallback_without_key():
    from app.config import settings
    from app.services.ai_proof_advisor import call_ai_proof_advisor

    original = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = None
    try:
        context = {"mandate_context": {}, "backend_checks": {}, "document_context": {}}
        result = call_ai_proof_advisor(context=context)
        assert result["risk_level"] == "warning"
        assert "ai_unavailable" in result["flags"]
    finally:
        settings.OPENAI_API_KEY = original
