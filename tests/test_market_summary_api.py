import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_get_schedule_null_when_absent():
    with patch("app.routers.market_summary.schedule_store.get_schedule", AsyncMock(return_value=None)):
        async with await _client() as ac:
            resp = await ac.get("/api/market-summary/US/schedule")
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.asyncio
async def test_get_schedule_invalid_market_404():
    async with await _client() as ac:
        resp = await ac.get("/api/market-summary/JP/schedule")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_put_schedule_rejects_bad_time():
    async with await _client() as ac:
        resp = await ac.put("/api/market-summary/US/schedule",
                            json={"send_time": "99:99", "days_of_week": [0], "enabled": True})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_schedule_upserts_sorted_days():
    with patch("app.routers.market_summary.schedule_store.upsert_schedule", AsyncMock()) as up:
        async with await _client() as ac:
            resp = await ac.put("/api/market-summary/KR/schedule",
                                json={"send_time": "18:00", "days_of_week": [4, 0, 1], "enabled": True})
    assert resp.status_code == 200
    up.assert_awaited_once()
    args = up.await_args.args
    assert args[1] == "market_summary_kr"  # feature_type
    assert args[2] == 0                     # target_id
    assert args[4] == "0,1,4"               # days


@pytest.mark.asyncio
async def test_send_now_invokes_service():
    with patch("app.routers.market_summary.summary_service.build_and_send",
               AsyncMock(return_value={"market": "US", "sent": True, "indices": 3,
                                       "holdings": 1, "watchlist": 0})):
        async with await _client() as ac:
            resp = await ac.post("/api/market-summary/US/send")
    assert resp.status_code == 200
    assert resp.json()["sent"] is True


@pytest.mark.asyncio
async def test_send_now_telegram_not_configured_409():
    from app.services.notification import telegram_service
    with patch("app.routers.market_summary.summary_service.build_and_send",
               AsyncMock(side_effect=telegram_service.TelegramNotConfigured("no token"))):
        async with await _client() as ac:
            resp = await ac.post("/api/market-summary/US/send")
    assert resp.status_code == 409
