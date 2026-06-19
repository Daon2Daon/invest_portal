import pytest
import pandas as pd
from unittest.mock import patch, AsyncMock

from app.models import Asset, Holding
from app.services.alert.basis import resolve_basis_price, clear_week52_cache


def _asset(**kw):
    base = dict(ticker="T", name="N", asset_type="stock", market="US",
                currency="USD", data_source="yfinance", fetch_symbol="T")
    base.update(kw)
    return Asset(**base)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_week52_cache()
    yield
    clear_week52_cache()


@pytest.mark.asyncio
async def test_absolute_returns_none(db_session):
    a = _asset(ticker="AAA", fetch_symbol="AAA")
    db_session.add(a); await db_session.commit()
    assert await resolve_basis_price(db_session, a, "ABSOLUTE") is None


@pytest.mark.asyncio
async def test_purchase_avg_weighted(db_session):
    a = _asset(ticker="BBB", fetch_symbol="BBB")
    db_session.add(a); await db_session.commit()
    db_session.add_all([
        Holding(asset_id=a.asset_id, quantity=10, purchase_price=100, fee=0),
        Holding(asset_id=a.asset_id, quantity=30, purchase_price=200, fee=0),
    ])
    await db_session.commit()
    # (10*100 + 30*200) / 40 = 175
    assert await resolve_basis_price(db_session, a, "PURCHASE_AVG") == 175.0


@pytest.mark.asyncio
async def test_purchase_avg_none_when_no_lots(db_session):
    a = _asset(ticker="CCC", fetch_symbol="CCC")
    db_session.add(a); await db_session.commit()
    assert await resolve_basis_price(db_session, a, "PURCHASE_AVG") is None


@pytest.mark.asyncio
async def test_week52_high_low_and_cache(db_session):
    a = _asset(ticker="DDD", fetch_symbol="DDD")
    db_session.add(a); await db_session.commit()
    df = pd.DataFrame({"High": [10.0, 30.0, 20.0], "Low": [5.0, 8.0, 6.0]})
    mock = AsyncMock(return_value=df)
    with patch("app.services.alert.basis.get_history", mock):
        assert await resolve_basis_price(db_session, a, "WEEK52_HIGH") == 30.0
        assert await resolve_basis_price(db_session, a, "WEEK52_LOW") == 5.0
    # 두 번째 호출은 캐시 사용 → get_history 1회만 호출
    assert mock.await_count == 1


@pytest.mark.asyncio
async def test_week52_none_when_no_history(db_session):
    a = _asset(ticker="EEE", fetch_symbol="EEE")
    db_session.add(a); await db_session.commit()
    with patch("app.services.alert.basis.get_history", AsyncMock(return_value=None)):
        assert await resolve_basis_price(db_session, a, "WEEK52_HIGH") is None
