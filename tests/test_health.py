import pytest


@pytest.mark.anyio("asyncio")
async def test_healthcheck(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
