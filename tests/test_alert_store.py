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


@pytest.mark.asyncio
async def test_list_all_alerts_view_groups_and_enriches(db_session, monkeypatch):
    from app.services.market.quote_service import get_quote  # noqa: F401 (참조 경로 확인용)
    a1 = _asset(ticker="ALLA", name="에이", fetch_symbol="ALLA")
    a2 = _asset(ticker="ALLB", name="비", fetch_symbol="ALLB")
    inactive = _asset(ticker="ALLC", fetch_symbol="ALLC", is_active=False)
    db_session.add_all([a1, a2, inactive]); await db_session.commit()
    await alert_store.create_alert(db_session, a1.asset_id, "ABSOLUTE", "ABOVE", 100.0)
    await alert_store.create_alert(db_session, a1.asset_id, "ABSOLUTE", "BELOW", 50.0)
    await alert_store.create_alert(db_session, a2.asset_id, "ABSOLUTE", "ABOVE", 10.0)
    await alert_store.create_alert(db_session, inactive.asset_id, "ABSOLUTE", "ABOVE", 1.0)
    await db_session.commit()

    calls = {"n": 0}
    from types import SimpleNamespace
    async def fake_quote(asset):
        calls["n"] += 1
        return SimpleNamespace(price=75.0, status="ok")
    monkeypatch.setattr("app.services.alert.alert_store.get_quote", fake_quote)

    rows = await alert_store.list_all_alerts_view(db_session)
    # 비활성 자산 제외 → 3건
    assert len(rows) == 3
    # 자산당 quote 1회(2개 활성 자산) — 알림 3건이어도 호출 2회
    assert calls["n"] == 2
    # 자산 메타 포함
    assert {r["asset_name"] for r in rows} == {"에이", "비"}
    assert all("ticker" in r and "target_price" in r for r in rows)
