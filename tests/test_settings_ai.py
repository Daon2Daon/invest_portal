import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from app.main import app


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_get_ai_masks_api_key():
    async def fake_get(_db, _cat, key):
        return {"base_url": "http://gw", "api_key": "SECRET",
                "model": "m", "prompt": "P", "enabled": "true"}.get(key)
    with patch("app.routers.settings.get_setting", AsyncMock(side_effect=fake_get)):
        async with await _client() as ac:
            resp = await ac.get("/api/settings/ai")
    body = resp.json()
    assert resp.status_code == 200
    assert body["api_key_set"] is True
    assert "api_key" not in body
    assert body["base_url"] == "http://gw"
    assert body["enabled"] is True


@pytest.mark.asyncio
async def test_put_ai_skips_empty_api_key():
    calls = []

    async def fake_set(_db, cat, key, value, is_secret=False, value_type="string"):
        calls.append((key, value, is_secret))

    with patch("app.routers.settings.set_setting", AsyncMock(side_effect=fake_set)):
        async with await _client() as ac:
            resp = await ac.put("/api/settings/ai", json={
                "base_url": "http://gw", "api_key": "", "model": "m", "enabled": True})
    assert resp.status_code == 200
    keys = [c[0] for c in calls]
    assert "api_key" not in keys
    assert ("base_url", "http://gw", False) in calls
    assert ("enabled", "true", False) in calls


@pytest.mark.asyncio
async def test_ai_models_returns_error_when_no_base_url():
    async def fake_get(_db, _cat, key):
        return None
    with patch("app.routers.settings.get_setting", AsyncMock(side_effect=fake_get)):
        async with await _client() as ac:
            resp = await ac.get("/api/settings/ai/models")
    assert resp.status_code == 200
    assert resp.json()["models"] == []
    assert "error" in resp.json()


@pytest.mark.asyncio
async def test_ai_models_lists_from_gateway():
    async def fake_get(_db, _cat, key):
        return {"base_url": "http://gw", "api_key": "K"}.get(key)
    with patch("app.routers.settings.get_setting", AsyncMock(side_effect=fake_get)), \
         patch("app.routers.settings.llm_client.list_models",
               AsyncMock(return_value=["gemini/a"])):
        async with await _client() as ac:
            resp = await ac.get("/api/settings/ai/models")
    assert resp.json()["models"] == ["gemini/a"]
