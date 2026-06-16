import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.ai import chart_analyzer
from app.services.ai.llm_client import LiteLLMError


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _asset():
    a = MagicMock()
    a.ticker, a.name, a.market, a.currency = "005930", "삼성전자", "KR", "KRW"
    return a


@pytest.mark.asyncio
async def test_analyze_returns_text():
    with patch("app.routers.charts._build_png", AsyncMock(return_value=b"\x89PNG")), \
         patch("app.routers.charts.chart_analyzer.analyze_raw",
               AsyncMock(return_value="**요약**\n\n두번째")), \
         patch("app.db.AsyncSession.get", AsyncMock(return_value=_asset())):
        async with await _client() as ac:
            resp = await ac.post("/api/charts/1/analyze")
    assert resp.status_code == 200
    assert resp.json()["analysis"] == "**요약**\n\n두번째"


@pytest.mark.asyncio
async def test_analyze_disabled_returns_409():
    with patch("app.routers.charts._build_png", AsyncMock(return_value=b"\x89PNG")), \
         patch("app.routers.charts.chart_analyzer.analyze_raw",
               AsyncMock(side_effect=chart_analyzer.AnalysisDisabled("off"))), \
         patch("app.db.AsyncSession.get", AsyncMock(return_value=_asset())):
        async with await _client() as ac:
            resp = await ac.post("/api/charts/1/analyze")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_analyze_gateway_error_returns_502():
    with patch("app.routers.charts._build_png", AsyncMock(return_value=b"\x89PNG")), \
         patch("app.routers.charts.chart_analyzer.analyze_raw",
               AsyncMock(side_effect=LiteLLMError("boom"))), \
         patch("app.db.AsyncSession.get", AsyncMock(return_value=_asset())):
        async with await _client() as ac:
            resp = await ac.post("/api/charts/1/analyze")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_send_telegram_best_effort_when_ai_disabled():
    quote = MagicMock(price=70000)
    with patch("app.routers.charts._build_png", AsyncMock(return_value=b"\x89PNG")), \
         patch("app.routers.charts.get_quote", AsyncMock(return_value=quote)), \
         patch("app.routers.charts.telegram_service.send_photo", AsyncMock(return_value=True)), \
         patch("app.routers.charts.chart_analyzer.analyze",
               AsyncMock(side_effect=chart_analyzer.AnalysisDisabled("off"))), \
         patch("app.db.AsyncSession.get", AsyncMock(return_value=_asset())):
        async with await _client() as ac:
            resp = await ac.post("/api/charts/1/send-telegram")
    body = resp.json()
    assert resp.status_code == 200
    assert body["sent"] == 2
    assert body["analysis_sent"] is False


@pytest.mark.asyncio
async def test_send_telegram_sends_analysis_when_enabled():
    quote = MagicMock(price=70000)
    with patch("app.routers.charts._build_png", AsyncMock(return_value=b"\x89PNG")), \
         patch("app.routers.charts.get_quote", AsyncMock(return_value=quote)), \
         patch("app.routers.charts.telegram_service.send_photo", AsyncMock(return_value=True)), \
         patch("app.routers.charts.telegram_service.send_message", AsyncMock(return_value=True)) as sm, \
         patch("app.routers.charts.chart_analyzer.analyze",
               AsyncMock(return_value=["<b>분석</b>"])), \
         patch("app.db.AsyncSession.get", AsyncMock(return_value=_asset())):
        async with await _client() as ac:
            resp = await ac.post("/api/charts/1/send-telegram")
    assert resp.json()["analysis_sent"] is True
    sm.assert_awaited_once()
