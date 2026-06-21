import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.scheduler.schedule_store import FEATURE_RISK


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_get_settings():
    cfg = {"enabled": True, "sig_rsi": True, "threshold_asset_pct": 30.0}
    with patch("app.routers.risk_signal.risk_service.load_config", AsyncMock(return_value=cfg)):
        async with await _client() as ac:
            resp = await ac.get("/api/risk-signal/settings")
    assert resp.status_code == 200 and resp.json()["enabled"] is True


@pytest.mark.asyncio
async def test_put_settings():
    store = {}

    async def fake_set(db, cat, key, val, is_secret=False):
        store[(cat, key)] = val

    with patch("app.routers.risk_signal.set_setting", fake_set):
        async with await _client() as ac:
            resp = await ac.put("/api/risk-signal/settings",
                                json={"enabled": True, "sig_rsi": False, "threshold_asset_pct": 25})
    assert resp.status_code == 200
    assert store[("risk_signal", "enabled")] == "true"
    assert store[("risk_signal", "sig_rsi")] == "false"
    assert store[("risk_signal", "threshold_asset_pct")] == "25.0"


@pytest.mark.asyncio
async def test_preview_returns_text():
    with patch("app.routers.risk_signal.risk_service.build_digest",
               AsyncMock(return_value="다이제스트 텍스트")):
        async with await _client() as ac:
            resp = await ac.post("/api/risk-signal/preview")
    assert resp.status_code == 200 and resp.json()["text"] == "다이제스트 텍스트"


@pytest.mark.asyncio
async def test_send_409_when_telegram_not_configured():
    from app.services.notification import telegram_service
    with patch("app.routers.risk_signal.risk_service.build_and_send",
               AsyncMock(side_effect=telegram_service.TelegramNotConfigured("no"))):
        async with await _client() as ac:
            resp = await ac.post("/api/risk-signal/send")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_schedule_routes():
    from unittest.mock import MagicMock
    with patch("app.routers.risk_signal.schedule_store.upsert_schedule", AsyncMock()) as up, \
         patch("app.routers.risk_signal.schedule_store.get_schedule",
               AsyncMock(return_value=MagicMock(send_time="08:00", days_of_week="0,1,2,3,4", enabled=True))), \
         patch("app.routers.risk_signal.schedule_store.delete_schedule", AsyncMock()):
        async with await _client() as ac:
            put = await ac.put("/api/risk-signal/schedule",
                               json={"send_time": "08:00", "days_of_week": [0, 1, 2], "enabled": True})
            get = await ac.get("/api/risk-signal/schedule")
            dele = await ac.delete("/api/risk-signal/schedule")
    assert put.status_code == 200 and get.json()["send_time"] == "08:00" and dele.status_code == 200
    assert up.call_args.args[1] == FEATURE_RISK and up.call_args.args[2] == 0
