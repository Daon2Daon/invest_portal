import pytest
from datetime import date
from app.services.snapshot.snapshot_service import build_snapshot_row
from app.services.snapshot import snapshot_service, snapshot_store


def test_build_snapshot_row_maps_summary_and_allocation():
    portfolio = {
        "summary": {
            "total_value_krw": 1500.0,
            "total_cost_krw": 1200.0,
            "total_profit_loss_krw": 250.0,
            "total_profit_loss_pct": 20.8,
            "total_cash_krw": 300.0,
        },
        "allocation": [
            {"asset_class": "주식", "value_krw": 900.0, "weight_pct": 60.0},
            {"asset_class": "현금성", "value_krw": 300.0, "weight_pct": 20.0},
        ],
    }
    row = build_snapshot_row(portfolio, date(2026, 6, 20))
    assert row["date"] == date(2026, 6, 20)
    assert row["total_value_krw"] == 1500.0
    assert row["total_cost_krw"] == 1200.0
    assert row["total_pl_krw"] == 250.0
    assert row["total_cash_krw"] == 300.0
    assert row["allocation"] == [
        {"asset_class": "주식", "value_krw": 900.0},
        {"asset_class": "현금성", "value_krw": 300.0},
    ]


@pytest.mark.asyncio
async def test_capture_daily_snapshot_empty_portfolio(db_session):
    snap = await snapshot_service.capture_daily_snapshot(db_session)
    assert snap.id is not None
    assert float(snap.total_value_krw) == 0
    rows = await snapshot_store.list_snapshots(db_session, None)
    assert len(rows) == 1
    assert rows[0].date == snap.date
