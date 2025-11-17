"""Tests for AI Proof Advisor configuration defaults."""


def test_ai_proof_disabled_by_default():
    from app.config import settings

    # AI Proof Advisor must be disabled by default for safety
    assert settings.AI_PROOF_ADVISOR_ENABLED is False
