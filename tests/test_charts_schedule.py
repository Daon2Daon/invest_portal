import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _asset():
    a = MagicMock()
    a.asset_id = 1
    return a


def _schedule_row():
    s = MagicMock()
    s.send_time = "08:30"
    s.days_of_week = "0,1,2,3,4"
    s.enabled = True
    return s


@pytest.mark.asyncio
async def test_get_schedule_null_when_absent():
    with patch("app.routers.charts.schedule_store.get_schedule", AsyncMock(return_value=None)):
        async with await _client() as ac:
            resp = await ac.get("/api/charts/1/schedule")
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.asyncio
async def test_get_schedule_returns_parsed():
    with patch("app.routers.charts.schedule_store.get_schedule", AsyncMock(return_value=_schedule_row())):
        async with await _client() as ac:
            resp = await ac.get("/api/charts/1/schedule")
    body = resp.json()
    assert body["send_time"] == "08:30"
    assert body["days_of_week"] == [0, 1, 2, 3, 4]
    assert body["enabled"] is True


@pytest.mark.asyncio
async def test_put_schedule_rejects_bad_time():
    async with await _client() as ac:
        resp = await ac.put("/api/charts/1/schedule",
                            json={"send_time": "25:00", "days_of_week": [0], "enabled": True})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_schedule_rejects_bad_day():
    async with await _client() as ac:
        resp = await ac.put("/api/charts/1/schedule",
                            json={"send_time": "08:00", "days_of_week": [7], "enabled": True})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_schedule_upserts():
    with patch("app.db.AsyncSession.get", AsyncMock(return_value=_asset())), \
         patch("app.routers.charts.schedule_store.upsert_schedule", AsyncMock()) as up:
        async with await _client() as ac:
            resp = await ac.put("/api/charts/1/schedule",
                                json={"send_time": "08:30", "days_of_week": [4, 0, 1], "enabled": True})
    assert resp.status_code == 200
    up.assert_awaited_once()
    # days는 정렬·중복제거된 콤마 문자열로 저장
    args = up.await_args.args
    assert args[4] == "0,1,4"


@pytest.mark.asyncio
async def test_put_schedule_404_when_asset_missing():
    with patch("app.db.AsyncSession.get", AsyncMock(return_value=None)):
        async with await _client() as ac:
            resp = await ac.put("/api/charts/1/schedule",
                                json={"send_time": "08:30", "days_of_week": [0], "enabled": True})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_schedule_ok():
    with patch("app.routers.charts.schedule_store.delete_schedule", AsyncMock(return_value=True)):
        async with await _client() as ac:
            resp = await ac.delete("/api/charts/1/schedule")
    assert resp.status_code == 200
