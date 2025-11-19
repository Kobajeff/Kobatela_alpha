from app.services import ai_proof_flags


class StubSettings:
    AI_PROOF_ADVISOR_ENABLED = False
    AI_PROOF_ADVISOR_MODEL = "gpt-test"
    AI_PROOF_ADVISOR_PROVIDER = "openai"
    AI_PROOF_TIMEOUT_SECONDS = 30


def test_ai_flags_reflect_live_settings(monkeypatch):
    stub = StubSettings()
    monkeypatch.setattr("app.services.ai_proof_flags.get_settings", lambda: stub)

    assert ai_proof_flags.ai_enabled() is False
    assert ai_proof_flags.ai_model() == "gpt-test"
    assert ai_proof_flags.ai_provider() == "openai"
    assert ai_proof_flags.ai_timeout_seconds() == 30

    stub.AI_PROOF_ADVISOR_ENABLED = True
    stub.AI_PROOF_TIMEOUT_SECONDS = 45

    assert ai_proof_flags.ai_enabled() is True
    assert ai_proof_flags.ai_timeout_seconds() == 45
