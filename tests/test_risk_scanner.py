import pytest
import pandas as pd
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.risk_signal import scanner


_CFG = {"sig_rsi": True, "sig_macd": False, "sig_bollinger": False, "sig_ma": False,
        "sig_concentration_asset": True, "sig_concentration_class": False,
        "threshold_asset_pct": 30.0, "threshold_class_pct": 60.0}


def _portfolio():
    return {
        "positions": [{"asset_id": 1, "ticker": "005930", "name": "삼성", "weight_pct": 62.0}],
        "allocation": [{"asset_class": "주식", "weight_pct": 62.0}],
    }


def _ind_df(rsi_last: float):
    return pd.DataFrame([
        {"RSI": 50, "MACD": 0, "Signal": 0, "Close": 10, "BB_upper": 99, "BB_lower": 1, "SMA50": 10},
        {"RSI": rsi_last, "MACD": 0, "Signal": 0, "Close": 10, "BB_upper": 99, "BB_lower": 1, "SMA50": 10},
    ])


@pytest.mark.asyncio
async def test_scan_collects_technical_and_concentration():
    raw = pd.DataFrame({"Close": [1, 2]})
    with patch("app.services.risk_signal.scanner.get_portfolio", AsyncMock(return_value=_portfolio())), \
         patch("app.services.risk_signal.scanner.get_history", AsyncMock(return_value=raw)), \
         patch("app.services.risk_signal.scanner.calculate_indicators", return_value=_ind_df(75)):
        db = MagicMock()
        db.get = AsyncMock(return_value=MagicMock())
        signals = await scanner.scan(db, _CFG)
    assert any(s["category"] == "technical" and s["type"] == "RSI" for s in signals)
    assert any(s["category"] == "concentration" and s["type"] == "종목 과중" for s in signals)


@pytest.mark.asyncio
async def test_scan_skips_asset_without_history():
    with patch("app.services.risk_signal.scanner.get_portfolio", AsyncMock(return_value=_portfolio())), \
         patch("app.services.risk_signal.scanner.get_history", AsyncMock(return_value=None)):
        db = MagicMock()
        db.get = AsyncMock(return_value=MagicMock())
        signals = await scanner.scan(db, _CFG)
    assert not any(s["category"] == "technical" for s in signals)
    assert any(s["category"] == "concentration" for s in signals)


@pytest.mark.asyncio
async def test_scan_skips_when_asset_missing():
    with patch("app.services.risk_signal.scanner.get_portfolio", AsyncMock(return_value=_portfolio())), \
         patch("app.services.risk_signal.scanner.get_history", AsyncMock(side_effect=AssertionError("불려선 안 됨"))):
        db = MagicMock()
        db.get = AsyncMock(return_value=None)
        signals = await scanner.scan(db, _CFG)
    assert not any(s["category"] == "technical" for s in signals)
