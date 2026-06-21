import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.ai_report import report_dispatch


@pytest.mark.asyncio
async def test_send_report_splits_and_sends():
    report = MagicMock(content_md="**제목**\n본문")
    with patch("app.services.ai_report.report_dispatch.telegram_service.send_message",
               AsyncMock(return_value=True)) as sm, \
         patch("app.services.ai_report.report_dispatch.asyncio.sleep", AsyncMock()):
        sent = await report_dispatch.send_report(MagicMock(), report)
    assert sent == 1
    assert "<b>제목</b>" in sm.call_args.args[1]
