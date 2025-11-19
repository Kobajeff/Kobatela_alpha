import pytest


@pytest.mark.anyio("asyncio")
async def test_healthcheck(client):
    response = await client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["psp_webhook_secret_status"] in {"missing", "partial", "ok"}
    assert isinstance(payload["scheduler_config_enabled"], bool)
    assert isinstance(payload["scheduler_running"], bool)
    assert "psp_webhook_secret_fingerprints" in payload
    fps = payload["psp_webhook_secret_fingerprints"]
    assert "primary" in fps
    assert "next" in fps
