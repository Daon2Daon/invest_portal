import pytest
from unittest.mock import patch, AsyncMock

from app.models import Asset, Holding
from app.services.market_summary import summary_service


def _asset(**kw):
    base = dict(ticker="T", name="N", asset_type="stock", market="US",
                currency="USD", data_source="yfinance", fetch_symbol="T")
    base.update(kw)
    return Asset(**base)


@pytest.mark.asyncio
async def test_build_and_send_filters_market_and_classifies(db_session):
    us_held = _asset(ticker="AAPL", fetch_symbol="AAPL", market="US")
    us_watch = _asset(ticker="TSLA", fetch_symbol="TSLA", market="US")
    kr = _asset(ticker="005930", fetch_symbol="005930", market="KR")
    db_session.add_all([us_held, us_watch, kr])
    await db_session.commit()
    db_session.add(Holding(asset_id=us_held.asset_id, quantity=1, purchase_price=10, fee=0))
    await db_session.commit()

    stats = {"current": 100.0, "daily_pct": 1.0, "weekly_pct": 2.0,
             "monthly_pct": 3.0, "wk52_high": 120.0, "wk52_drop_pct": -16.7}
    sent = AsyncMock(return_value=True)
    with patch("app.services.market_summary.summary_service.index_lines",
               AsyncMock(return_value=[{"name": "S&P 500", "price": 5000.0, "change_pct": 1.0}])), \
         patch("app.services.market_summary.summary_service.asset_stats", AsyncMock(return_value=stats)), \
         patch("app.services.market_summary.summary_service.telegram_service.send_message", sent):
        res = await summary_service.build_and_send(db_session, "US")

    assert res["market"] == "US"
    assert res["holdings"] == 1     # AAPL
    assert res["watchlist"] == 1    # TSLA (KR 제외)
    assert res["sent"] is True
    sent.assert_awaited_once()
    msg = sent.await_args.args[1]
    assert "AAPL" in msg and "TSLA" in msg and "005930" not in msg


@pytest.mark.asyncio
async def test_build_and_send_skips_assets_without_stats(db_session):
    a = _asset(ticker="NOHIST", fetch_symbol="NOHIST", market="US")
    db_session.add(a); await db_session.commit()
    with patch("app.services.market_summary.summary_service.index_lines", AsyncMock(return_value=[])), \
         patch("app.services.market_summary.summary_service.asset_stats", AsyncMock(return_value=None)), \
         patch("app.services.market_summary.summary_service.telegram_service.send_message", AsyncMock(return_value=True)):
        res = await summary_service.build_and_send(db_session, "US")
    assert res["holdings"] == 0 and res["watchlist"] == 0


from unittest.mock import MagicMock
import app.services.scheduler.handlers as handlers
from app.services.scheduler.schedule_store import FEATURE_SUMMARY_US


@pytest.mark.asyncio
async def test_handler_skips_on_holiday():
    sched = MagicMock(feature_type=FEATURE_SUMMARY_US)
    bsend = AsyncMock()
    with patch.object(handlers, "is_trading_day", return_value=False), \
         patch.object(handlers.summary_service, "build_and_send", bsend):
        await handlers.handle_market_summary(MagicMock(), sched)
    bsend.assert_not_awaited()


@pytest.mark.asyncio
async def test_handler_sends_on_trading_day():
    sched = MagicMock(feature_type=FEATURE_SUMMARY_US)
    bsend = AsyncMock(return_value={"sent": True})
    with patch.object(handlers, "is_trading_day", return_value=True), \
         patch.object(handlers.summary_service, "build_and_send", bsend):
        await handlers.handle_market_summary(MagicMock(), sched)
    bsend.assert_awaited_once()
    assert bsend.await_args.args[1] == "US"


def test_handlers_registry_has_market_summary():
    from app.services.scheduler.schedule_store import FEATURE_SUMMARY_KR
    assert handlers.HANDLERS[FEATURE_SUMMARY_US] is handlers.handle_market_summary
    assert handlers.HANDLERS[FEATURE_SUMMARY_KR] is handlers.handle_market_summary
