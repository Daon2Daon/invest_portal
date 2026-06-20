from datetime import date
from app.services.snapshot.snapshot_service import build_snapshot_row


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
