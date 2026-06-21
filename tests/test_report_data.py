import pytest
from app.services.ai_report import report_data as rd


def test_pct_change_basic():
    assert rd.pct_change([100, 110], 1) == pytest.approx(10.0)
    assert rd.pct_change([100, 90], 1) == pytest.approx(-10.0)


def test_pct_change_insufficient_returns_none():
    assert rd.pct_change([100], 1) is None
    assert rd.pct_change([], 5) is None


def test_build_input_block_contains_sections():
    portfolio = {
        "summary": {"total_value_krw": 1000.0, "total_cost_krw": 600.0,
                    "total_profit_loss_krw": 400.0, "total_profit_loss_pct": 66.7,
                    "total_cash_krw": 100.0},
        "allocation": [{"asset_class": "주식", "value_krw": 600.0, "weight_pct": 60.0},
                       {"asset_class": "현금성", "value_krw": 100.0, "weight_pct": 10.0}],
        "positions": [{"asset_id": 1, "ticker": "005930", "name": "삼성전자",
                       "asset_class": "주식", "value_krw": 600.0, "weight_pct": 60.0,
                       "profit_loss_krw": 100.0, "profit_loss_pct": 20.0}],
    }
    trend = [{"date": "2026-06-20", "total_value_krw": 990.0, "total_pl_krw": 390.0}]
    returns = {1: {"w1": 1.5, "m1": -3.0}}
    block = rd.build_input_block(portfolio, trend, returns, today="2026-06-21")
    assert "2026-06-21" in block
    assert "삼성전자" in block and "005930" in block
    assert "주식" in block
    assert "1.5%" in block and "-3.0%" in block
    assert "2026-06-20" in block


def test_build_input_block_no_history_fallback():
    portfolio = {
        "summary": {"total_value_krw": 100.0, "total_cost_krw": 100.0,
                    "total_profit_loss_krw": 0.0, "total_profit_loss_pct": 0.0,
                    "total_cash_krw": 0.0},
        "allocation": [],
        "positions": [{"asset_id": 9, "ticker": "X", "name": "수동채권",
                       "asset_class": "채권", "value_krw": 100.0, "weight_pct": 100.0,
                       "profit_loss_krw": 0.0, "profit_loss_pct": 0.0}],
    }
    block = rd.build_input_block(portfolio, [], {9: None}, today="2026-06-21")
    assert "(이력 없음)" in block
