import pytest
from app.models import Asset, PriceAlert


def _asset(**kw):
    base = dict(ticker="T", name="N", asset_type="stock", market="US",
                currency="USD", data_source="yfinance", fetch_symbol="T")
    base.update(kw)
    return Asset(**base)


@pytest.mark.asyncio
async def test_create_price_alert_row(db_session):
    a = _asset(ticker="AAA", fetch_symbol="AAA")
    db_session.add(a)
    await db_session.commit()
    alert = PriceAlert(asset_id=a.asset_id, basis="ABSOLUTE", direction="ABOVE", value=250)
    db_session.add(alert)
    await db_session.commit()
    assert alert.alert_id is not None
    assert alert.enabled is True
    assert alert.is_triggered is False
