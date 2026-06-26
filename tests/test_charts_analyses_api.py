import pytest
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_list_analyses():
    rows = [
        MagicMock(id=2, asset_id=1, content_md="## B", model="m", trigger="manual",
                  created_at=datetime(2026, 6, 26, 9, tzinfo=timezone.utc)),
        MagicMock(id=1, asset_id=1, content_md="## A", model="m", trigger="scheduled",
                  created_at=datetime(2026, 6, 25, 9, tzinfo=timezone.utc)),
    ]
    with patch("app.routers.charts.analysis_store.list_for_asset",
               AsyncMock(return_value=rows)):
        async with await _client() as ac:
            resp = await ac.get("/api/charts/1/analyses")
    assert resp.status_code == 200
    body = resp.json()
    assert [r["id"] for r in body] == [2, 1]
    assert body[0]["content_md"] == "## B"
    assert body[0]["trigger"] == "manual"


@pytest.mark.asyncio
async def test_delete_analysis_found():
    with patch("app.routers.charts.analysis_store.delete", AsyncMock(return_value=True)):
        async with await _client() as ac:
            resp = await ac.delete("/api/charts/analyses/5")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_delete_analysis_missing_404():
    with patch("app.routers.charts.analysis_store.delete", AsyncMock(return_value=False)):
        async with await _client() as ac:
            resp = await ac.delete("/api/charts/analyses/999")
    assert resp.status_code == 404
