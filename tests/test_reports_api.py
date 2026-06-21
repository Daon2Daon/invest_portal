import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.ai_report import report_dispatch
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.ai_report import report_generator


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _report(id=1):
    r = MagicMock()
    r.id, r.title, r.content_md, r.model, r.trigger = id, "제목", "## 본문", "gemini/x", "manual"
    r.created_at = MagicMock()
    r.created_at.isoformat = MagicMock(return_value="2026-06-21T06:30:00+09:00")
    return r


@pytest.mark.asyncio
async def test_post_report_creates():
    with patch("app.routers.reports.report_generator.create_report",
               AsyncMock(return_value=_report())):
        async with await _client() as ac:
            resp = await ac.post("/api/reports")
    assert resp.status_code == 200
    assert resp.json()["content_md"] == "## 본문"


@pytest.mark.asyncio
async def test_post_report_disabled_409():
    with patch("app.routers.reports.report_generator.create_report",
               AsyncMock(side_effect=report_generator.ReportDisabled("off"))):
        async with await _client() as ac:
            resp = await ac.post("/api/reports")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_post_report_gateway_error_502():
    from app.services.ai.llm_client import LiteLLMError
    with patch("app.routers.reports.report_generator.create_report",
               AsyncMock(side_effect=LiteLLMError("boom"))):
        async with await _client() as ac:
            resp = await ac.post("/api/reports")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_get_list_and_detail_and_delete():
    with patch("app.routers.reports.report_store.list_reports",
               AsyncMock(return_value=[_report(2), _report(1)])), \
         patch("app.routers.reports.report_store.get_report",
               AsyncMock(return_value=_report(1))), \
         patch("app.routers.reports.report_store.delete_report",
               AsyncMock(return_value=True)):
        async with await _client() as ac:
            lst = await ac.get("/api/reports")
            detail = await ac.get("/api/reports/1")
            dele = await ac.delete("/api/reports/1")
    assert len(lst.json()) == 2
    assert detail.json()["id"] == 1
    assert dele.status_code == 200


@pytest.mark.asyncio
async def test_detail_404():
    with patch("app.routers.reports.report_store.get_report", AsyncMock(return_value=None)):
        async with await _client() as ac:
            resp = await ac.get("/api/reports/999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_send_telegram_409_when_not_configured():
    from app.services.notification import telegram_service
    with patch("app.routers.reports.report_store.get_report", AsyncMock(return_value=_report(1))), \
         patch("app.routers.reports.report_dispatch.send_report",
               AsyncMock(side_effect=telegram_service.TelegramNotConfigured("no"))):
        async with await _client() as ac:
            resp = await ac.post("/api/reports/1/send-telegram")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_send_report_splits_and_sends():
    report = MagicMock(content_md="**제목**\n본문")
    with patch("app.services.ai_report.report_dispatch.telegram_service.send_message",
               AsyncMock(return_value=True)) as sm, \
         patch("app.services.ai_report.report_dispatch.asyncio.sleep", AsyncMock()):
        sent = await report_dispatch.send_report(MagicMock(), report)
    assert sent == 1
    assert "<b>제목</b>" in sm.call_args.args[1]
