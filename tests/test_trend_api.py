from datetime import date
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.routers.trend import period_to_since


def test_period_to_since_known_periods():
    today = date(2026, 6, 20)
    assert period_to_since("1M", today) == date(2026, 5, 21)
    assert period_to_since("3M", today) == date(2026, 3, 22)
    assert period_to_since("1Y", today) == date(2025, 6, 20)
    assert period_to_since("ALL", today) is None
    assert period_to_since("XX", today) == date(2026, 5, 21)


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_trend_returns_serialized_rows():
    class _Snap:
        date = date(2026, 6, 20)
        total_value_krw = 1500
        total_cost_krw = 1200
        total_pl_krw = 300
        total_cash_krw = 100
        allocation = [{"asset_class": "주식", "value_krw": 1400}]
    with patch("app.routers.trend.snapshot_store.list_snapshots",
               AsyncMock(return_value=[_Snap()])):
        async with await _client() as ac:
            resp = await ac.get("/api/trend?period=1M")
    assert resp.status_code == 200
    body = resp.json()
    assert body == [{
        "date": "2026-06-20",
        "total_value_krw": 1500.0,
        "total_cost_krw": 1200.0,
        "total_pl_krw": 300.0,
        "total_cash_krw": 100.0,
        "allocation": [{"asset_class": "주식", "value_krw": 1400}],
    }]
