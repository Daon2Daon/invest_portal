from datetime import date
import pytest
from app.models import PortfolioSnapshot
from app.services.snapshot import snapshot_store


@pytest.mark.asyncio
async def test_insert_and_read_snapshot(db_session):
    snap = PortfolioSnapshot(
        date=date(2026, 6, 20),
        total_value_krw=1000, total_cost_krw=800,
        total_pl_krw=200, total_cash_krw=100,
        allocation=[{"asset_class": "주식", "value_krw": 900}],
    )
    db_session.add(snap)
    await db_session.commit()
    assert snap.id is not None
    assert snap.allocation[0]["asset_class"] == "주식"


def _row(d: date, value: float):
    return {"date": d, "total_value_krw": value, "total_cost_krw": value,
            "total_pl_krw": 0, "total_cash_krw": 0,
            "allocation": [{"asset_class": "주식", "value_krw": value}]}


@pytest.mark.asyncio
async def test_upsert_is_idempotent_by_date(db_session):
    await snapshot_store.upsert_snapshot(db_session, _row(date(2026, 6, 20), 1000))
    snap = await snapshot_store.upsert_snapshot(db_session, _row(date(2026, 6, 20), 1234))
    rows = await snapshot_store.list_snapshots(db_session, None)
    assert len(rows) == 1
    assert float(snap.total_value_krw) == 1234


@pytest.mark.asyncio
async def test_list_snapshots_since_filter_and_order(db_session):
    await snapshot_store.upsert_snapshot(db_session, _row(date(2026, 6, 10), 1))
    await snapshot_store.upsert_snapshot(db_session, _row(date(2026, 6, 20), 2))
    await snapshot_store.upsert_snapshot(db_session, _row(date(2026, 6, 15), 3))
    rows = await snapshot_store.list_snapshots(db_session, date(2026, 6, 15))
    assert [r.date for r in rows] == [date(2026, 6, 15), date(2026, 6, 20)]
