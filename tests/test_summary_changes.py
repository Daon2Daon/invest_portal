import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, AsyncMock

from app.services.market_summary.changes import asset_stats


def _df(closes, highs=None, lows=None):
    n = len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "Open": closes, "High": highs or [c + 1 for c in closes],
        "Low": lows or [c - 1 for c in closes], "Close": closes,
        "Volume": np.ones(n) * 1000}, index=idx)


@pytest.mark.asyncio
async def test_asset_stats_periods_and_52w():
    closes = [100.0] * 30
    closes[-1] = 110.0   # 마지막만 110
    closes[-2] = 100.0
    df = _df(closes, highs=[120.0] * 30)  # 52주 고점 120
    with patch("app.services.market_summary.changes.get_history", AsyncMock(return_value=df)):
        s = await asset_stats(object())
    assert s["current"] == 110.0
    assert round(s["daily_pct"], 4) == 10.0           # 100→110
    assert s["wk52_high"] == 120.0
    assert round(s["wk52_drop_pct"], 4) == round((110 - 120) / 120 * 100, 4)


@pytest.mark.asyncio
async def test_asset_stats_none_when_insufficient():
    with patch("app.services.market_summary.changes.get_history", AsyncMock(return_value=None)):
        assert await asset_stats(object()) is None
    with patch("app.services.market_summary.changes.get_history", AsyncMock(return_value=_df([100.0]))):
        assert await asset_stats(object()) is None  # len < 2
