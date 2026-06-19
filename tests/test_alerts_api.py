import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models import PriceAlert


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _real_alert():
    a = PriceAlert(asset_id=1, basis="ABSOLUTE", direction="ABOVE", value=250.0)
    a.alert_id = 1
    a.enabled = True
    a.is_triggered = False
    a.note = None
    return a


@pytest.mark.asyncio
async def test_create_rejects_nonpositive_value():
    async with await _client() as ac:
        resp = await ac.post("/api/alerts", json={
            "asset_id": 1, "basis": "ABSOLUTE", "direction": "ABOVE", "value": 0})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_bad_basis():
    async with await _client() as ac:
        resp = await ac.post("/api/alerts", json={
            "asset_id": 1, "basis": "NOPE", "direction": "ABOVE", "value": 1})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_purchase_avg_requires_holdings():
    asset = MagicMock(data_source="yfinance")
    with patch("app.db.AsyncSession.get", AsyncMock(return_value=asset)), \
         patch("app.routers.alerts.alert_store.has_holdings", AsyncMock(return_value=False)):
        async with await _client() as ac:
            resp = await ac.post("/api/alerts", json={
                "asset_id": 1, "basis": "PURCHASE_AVG", "direction": "BELOW", "value": 15})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_week52_rejects_manual():
    asset = MagicMock(data_source="manual")
    with patch("app.db.AsyncSession.get", AsyncMock(return_value=asset)):
        async with await _client() as ac:
            resp = await ac.post("/api/alerts", json={
                "asset_id": 1, "basis": "WEEK52_HIGH", "direction": "BELOW", "value": 10})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_absolute_ok():
    asset = MagicMock(data_source="yfinance")
    with patch("app.db.AsyncSession.get", AsyncMock(return_value=asset)), \
         patch("app.routers.alerts.alert_store.create_alert", AsyncMock(return_value=_real_alert())):
        async with await _client() as ac:
            resp = await ac.post("/api/alerts", json={
                "asset_id": 1, "basis": "ABSOLUTE", "direction": "ABOVE", "value": 250})
    assert resp.status_code == 200
    assert resp.json()["basis"] == "ABSOLUTE"


@pytest.mark.asyncio
async def test_list_uses_view():
    rows = [{"alert_id": 1, "asset_id": 1, "basis": "ABSOLUTE", "direction": "ABOVE",
             "value": 250.0, "enabled": True, "is_triggered": False, "note": None,
             "target_price": 250.0, "current_price": 251.0, "price_status": "ok", "fired": True}]
    with patch("app.routers.alerts.list_alerts_view", AsyncMock(return_value=rows)):
        async with await _client() as ac:
            resp = await ac.get("/api/alerts?asset_id=1")
    assert resp.status_code == 200
    assert resp.json()[0]["fired"] is True


@pytest.mark.asyncio
async def test_rearm_calls_store():
    with patch("app.routers.alerts.alert_store.get_alert", AsyncMock(return_value=_real_alert())), \
         patch("app.routers.alerts.alert_store.rearm_alert", AsyncMock(return_value=_real_alert())) as r:
        async with await _client() as ac:
            resp = await ac.post("/api/alerts/1/rearm")
    assert resp.status_code == 200
    r.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_404_when_missing():
    with patch("app.routers.alerts.alert_store.get_alert", AsyncMock(return_value=None)):
        async with await _client() as ac:
            resp = await ac.delete("/api/alerts/99")
    assert resp.status_code == 404
