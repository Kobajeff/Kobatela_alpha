import pytest


@pytest.mark.anyio("asyncio")
async def test_healthcheck(client):
    response = await client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert isinstance(payload["psp_secrets_configured"], bool)
    assert isinstance(payload["scheduler_enabled"], bool)
