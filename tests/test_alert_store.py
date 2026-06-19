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


from app.services.alert import alert_store


@pytest.mark.asyncio
async def test_store_crud_and_rearm(db_session):
    a = _asset(ticker="STORE", fetch_symbol="STORE")
    db_session.add(a); await db_session.commit()
    alert = await alert_store.create_alert(
        db_session, a.asset_id, "ABSOLUTE", "ABOVE", 250.0, note="hi")
    assert alert.alert_id is not None

    # update
    alert = await alert_store.update_alert(db_session, alert, value=260.0, enabled=False)
    assert float(alert.value) == 260.0
    assert alert.enabled is False

    # simulate fired then rearm
    alert.is_triggered = True
    await db_session.commit()
    alert = await alert_store.rearm_alert(db_session, alert)
    assert alert.enabled is True
    assert alert.is_triggered is False
    assert alert.triggered_at is None

    # list_by_asset
    rows = await alert_store.list_by_asset(db_session, a.asset_id)
    assert len(rows) == 1

    # has_holdings False (no lots)
    assert await alert_store.has_holdings(db_session, a.asset_id) is False

    # delete
    await alert_store.delete_alert(db_session, alert)
    assert await alert_store.list_by_asset(db_session, a.asset_id) == []


@pytest.mark.asyncio
async def test_list_active_with_assets_filters(db_session):
    active = _asset(ticker="ACT", fetch_symbol="ACT")
    inactive = _asset(ticker="INA", fetch_symbol="INA", is_active=False)
    db_session.add_all([active, inactive]); await db_session.commit()
    # active asset: one enabled alert + one triggered (excluded)
    await alert_store.create_alert(db_session, active.asset_id, "ABSOLUTE", "ABOVE", 1.0)
    triggered = await alert_store.create_alert(db_session, active.asset_id, "ABSOLUTE", "ABOVE", 2.0)
    triggered.is_triggered = True
    # inactive asset alert (excluded by asset.is_active)
    await alert_store.create_alert(db_session, inactive.asset_id, "ABSOLUTE", "ABOVE", 3.0)
    await db_session.commit()
    pairs = await alert_store.list_active_with_assets(db_session)
    values = sorted(float(al.value) for al, _ in pairs)
    assert values == [1.0]
