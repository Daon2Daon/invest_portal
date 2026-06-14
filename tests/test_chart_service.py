import numpy as np
import pandas as pd
from app.services.chart.chart_service import calculate_indicators, to_weekly, generate_ta_chart


def _ohlcv(n=80):
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    base = np.linspace(100, 120, n)
    return pd.DataFrame({
        "Open": base, "High": base + 2, "Low": base - 2, "Close": base + 1,
        "Volume": np.arange(1, n + 1) * 1000.0}, index=idx)


def test_calculate_indicators_adds_columns_and_rsi_range():
    df = calculate_indicators(_ohlcv())
    for col in ["EMA12", "EMA26", "SMA20", "BB_upper", "BB_lower", "RSI", "MACD", "Signal", "Histogram"]:
        assert col in df.columns
    rsi = df["RSI"].dropna()
    assert (rsi >= 0).all() and (rsi <= 100).all()
    assert np.allclose((df["EMA12"] - df["EMA26"]).values, df["MACD"].values, equal_nan=True)


def test_to_weekly_aggregates():
    df = _ohlcv(14)
    w = to_weekly(df)
    assert len(w) <= 3
    assert {"Open", "High", "Low", "Close", "Volume"} <= set(w.columns)
    assert w["High"].iloc[0] >= df["High"].iloc[0]


def test_generate_ta_chart_returns_png_bytes():
    png = generate_ta_chart(_ohlcv(), ticker="TEST", name="테스트종목", timeframe="DAILY")
    assert isinstance(png, (bytes, bytearray))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1000
