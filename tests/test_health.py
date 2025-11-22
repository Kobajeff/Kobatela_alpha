import pytest


@pytest.mark.anyio("asyncio")
async def test_healthcheck(client):
    response = await client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert payload["psp_webhook_secret_status"] in {"missing", "partial", "ok"}
    assert isinstance(payload["scheduler_config_enabled"], bool)
    assert isinstance(payload["scheduler_running"], bool)
    assert "psp_webhook_secret_fingerprints" in payload
    fps = payload["psp_webhook_secret_fingerprints"]
    assert "primary" in fps
    assert "next" in fps
    assert payload.get("db_status") in {"ok", "error"}
    assert payload.get("migrations_status") in {"up_to_date", "out_of_date", "unknown"}
    assert isinstance(payload.get("db_ok"), bool)
    assert isinstance(payload.get("migrations_ok"), bool)
    assert "scheduler_lock" in payload
    assert payload.get("ai_metrics", {}).keys() >= {"calls", "errors"}
    assert payload.get("ocr_metrics", {}).keys() >= {"calls", "errors"}
    assert payload.get("ai_stats", {}).keys() >= {"calls", "errors"}


@pytest.mark.anyio("asyncio")
async def test_health_degrades_on_db_failure(monkeypatch, client):
    class BrokenEngine:
        def connect(self):  # pragma: no cover - simple stub
            raise RuntimeError("DB down")

    monkeypatch.setattr("app.routers.health.get_engine", lambda: BrokenEngine())

    response = await client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["db_status"] == "error"
    assert payload["migrations_status"] in {"unknown", "error", "out_of_date"}
    assert payload["db_ok"] is False
    assert payload["migrations_ok"] is False


@pytest.mark.anyio("asyncio")
async def test_health_contains_db_status_and_ai_stats(client):
    response = await client.get("/health")
    assert response.status_code == 200
    payload = response.json()

    assert payload["db_status"] in {"ok", "error"}
    assert "ai_stats" in payload
    assert payload["ai_stats"].keys() >= {"calls", "errors"}


@pytest.mark.anyio("asyncio")
async def test_health_status_degraded_when_db_status_error(monkeypatch, client):
    from app.routers import health as health_module

    monkeypatch.setattr(health_module, "_db_status", lambda: "error")

    response = await client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["db_status"] == "error"
