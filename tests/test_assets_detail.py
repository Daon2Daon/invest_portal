import pytest
from unittest.mock import patch, AsyncMock

from app.models import Asset, Holding
from app.services.market.types import Quote
from app.services.portfolio.portfolio_service import get_asset_detail


def _asset(**kw):
    base = dict(ticker="T", name="N", asset_type="stock", market="US",
                currency="USD", data_source="yfinance", fetch_symbol="T")
    base.update(kw)
    return Asset(**base)


@pytest.mark.asyncio
async def test_detail_none_when_missing(db_session):
    assert await get_asset_detail(db_session, 999999) is None


@pytest.mark.asyncio
async def test_detail_watchlist_no_holding(db_session):
    a = _asset(ticker="AAA", fetch_symbol="AAA")
    db_session.add(a)
    await db_session.commit()
    q = Quote(price=100.0, currency="USD", change_pct=1.0, status="ok")
    with patch("app.services.portfolio.portfolio_service.get_quote", AsyncMock(return_value=q)):
        d = await get_asset_detail(db_session, a.asset_id)
    assert d["held"] is False
    assert d["holding_summary"] is None
    assert d["quote"]["price"] == 100.0
    assert d["asset"]["ticker"] == "AAA"


@pytest.mark.asyncio
async def test_detail_held_has_summary(db_session):
    a = _asset(ticker="BBB", fetch_symbol="BBB")
    db_session.add(a)
    await db_session.commit()
    db_session.add(Holding(asset_id=a.asset_id, quantity=10, purchase_price=90, fee=0))
    await db_session.commit()
    q = Quote(price=100.0, currency="USD", status="ok")
    with patch("app.services.portfolio.portfolio_service.get_quote", AsyncMock(return_value=q)), \
         patch("app.services.portfolio.portfolio_service.get_rate_to_krw", AsyncMock(return_value=1300.0)):
        d = await get_asset_detail(db_session, a.asset_id)
    assert d["held"] is True
    assert d["holding_summary"]["quantity"] == 10
    assert d["holding_summary"]["avg_price"] == 90
    assert d["holding_summary"]["value_krw"] == 10 * 100 * 1300.0
