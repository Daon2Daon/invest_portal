import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.scheduler import handlers
from app.services.scheduler.schedule_store import FEATURE_RISK


def test_feature_risk_registered():
    assert FEATURE_RISK in handlers.HANDLERS


@pytest.mark.asyncio
async def test_handle_risk_signal_sends_when_enabled():
    sched = MagicMock(feature_type=FEATURE_RISK, target_id=0)
    with patch("app.services.scheduler.handlers.risk_service.load_config",
               AsyncMock(return_value={"enabled": True})), \
         patch("app.services.scheduler.handlers.risk_service.build_and_send",
               AsyncMock(return_value={"sent": True})) as bs:
        await handlers.handle_risk_signal(MagicMock(), sched)
    bs.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_risk_signal_skips_when_disabled():
    sched = MagicMock(feature_type=FEATURE_RISK, target_id=0)
    with patch("app.services.scheduler.handlers.risk_service.load_config",
               AsyncMock(return_value={"enabled": False})), \
         patch("app.services.scheduler.handlers.risk_service.build_and_send",
               AsyncMock(side_effect=AssertionError("발송되면 안 됨"))):
        await handlers.handle_risk_signal(MagicMock(), sched)


@pytest.mark.asyncio
async def test_handle_risk_signal_swallows_telegram_not_configured():
    from app.services.notification import telegram_service
    sched = MagicMock(feature_type=FEATURE_RISK, target_id=0)
    with patch("app.services.scheduler.handlers.risk_service.load_config",
               AsyncMock(return_value={"enabled": True})), \
         patch("app.services.scheduler.handlers.risk_service.build_and_send",
               AsyncMock(side_effect=telegram_service.TelegramNotConfigured("no"))):
        await handlers.handle_risk_signal(MagicMock(), sched)
