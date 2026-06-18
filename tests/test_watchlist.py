import pytest
from unittest.mock import patch, AsyncMock

from app.models import Asset, Holding
from app.services.market.types import Quote
from app.services.portfolio.portfolio_service import held_asset_ids
from app.services.portfolio.watchlist_service import get_watchlist


def _asset(**kw):
    base = dict(ticker="T", name="N", asset_type="stock", market="US",
                currency="USD", data_source="yfinance", fetch_symbol="T")
    base.update(kw)
    return Asset(**base)


@pytest.mark.asyncio
async def test_held_asset_ids(db_session):
    a1 = _asset(ticker="AAA", fetch_symbol="AAA")
    a2 = _asset(ticker="BBB", fetch_symbol="BBB")
    db_session.add_all([a1, a2])
    await db_session.commit()
    db_session.add(Holding(asset_id=a1.asset_id, quantity=1, purchase_price=10, fee=0))
    await db_session.commit()
    ids = await held_asset_ids(db_session)
    assert a1.asset_id in ids
    assert a2.asset_id not in ids


@pytest.mark.asyncio
async def test_get_watchlist_excludes_held(db_session):
    held = _asset(ticker="AAA", fetch_symbol="AAA")
    watch = _asset(ticker="BBB", fetch_symbol="BBB")
    db_session.add_all([held, watch])
    await db_session.commit()
    db_session.add(Holding(asset_id=held.asset_id, quantity=1, purchase_price=10, fee=0))
    await db_session.commit()
    q = Quote(price=100.0, currency="USD", change=2.0, change_pct=2.0, status="ok")
    with patch("app.services.portfolio.watchlist_service.get_quote", AsyncMock(return_value=q)):
        rows = await get_watchlist(db_session)
    assert {r["ticker"] for r in rows} == {"BBB"}
    assert rows[0]["current_price"] == 100.0
    assert rows[0]["change_pct"] == 2.0


@pytest.mark.asyncio
async def test_get_watchlist_error_quote_sets_price_none(db_session):
    a = _asset(ticker="CCC", fetch_symbol="CCC")
    db_session.add(a)
    await db_session.commit()
    q = Quote(price=0.0, currency="USD", status="error")
    with patch("app.services.portfolio.watchlist_service.get_quote", AsyncMock(return_value=q)):
        rows = await get_watchlist(db_session)
    assert rows[0]["current_price"] is None
    assert rows[0]["price_status"] == "error"
