import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.scheduler import handlers
from app.services.scheduler.schedule_store import FEATURE_REPORT


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def test_feature_report_registered():
    assert FEATURE_REPORT in handlers.HANDLERS


@pytest.mark.asyncio
async def test_handle_ai_report_generates_and_sends():
    sched = MagicMock(feature_type=FEATURE_REPORT, target_id=0)
    report = MagicMock()
    with patch("app.services.scheduler.handlers.report_generator.create_report",
               AsyncMock(return_value=report)) as cr, \
         patch("app.services.scheduler.handlers.report_dispatch.send_report",
               AsyncMock(return_value=1)) as sr:
        await handlers.handle_ai_report(MagicMock(), sched)
    assert cr.call_args.kwargs["trigger"] == "scheduled"
    sr.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_ai_report_telegram_not_configured_is_swallowed():
    from app.services.notification import telegram_service
    sched = MagicMock(feature_type=FEATURE_REPORT, target_id=0)
    with patch("app.services.scheduler.handlers.report_generator.create_report",
               AsyncMock(return_value=MagicMock())), \
         patch("app.services.scheduler.handlers.report_dispatch.send_report",
               AsyncMock(side_effect=telegram_service.TelegramNotConfigured("no"))):
        await handlers.handle_ai_report(MagicMock(), sched)   # 예외 없이 통과


@pytest.mark.asyncio
async def test_report_schedule_routes():
    with patch("app.routers.reports.schedule_store.upsert_schedule", AsyncMock()) as up, \
         patch("app.routers.reports.schedule_store.get_schedule",
               AsyncMock(return_value=MagicMock(send_time="06:30", days_of_week="0,1,2,3,4", enabled=True))), \
         patch("app.routers.reports.schedule_store.delete_schedule", AsyncMock()):
        async with await _client() as ac:
            put = await ac.put("/api/reports/schedule",
                               json={"send_time": "06:30", "days_of_week": [0, 1, 2], "enabled": True})
            get = await ac.get("/api/reports/schedule")
            dele = await ac.delete("/api/reports/schedule")
    assert put.status_code == 200
    assert get.json()["send_time"] == "06:30"
    assert dele.status_code == 200
    assert up.call_args.args[1] == FEATURE_REPORT and up.call_args.args[2] == 0
