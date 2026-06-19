import numpy as np
import pandas as pd

from app.services.chart.chart_service import _volume_profile, generate_ta_chart
from app.services.ai.chart_analyzer import DEFAULT_PROMPT


def _ohlcv(n=80):
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    base = np.linspace(100, 120, n)
    return pd.DataFrame({
        "Open": base, "High": base + 2, "Low": base - 2, "Close": base + 1,
        "Volume": np.arange(1, n + 1) * 1000.0}, index=idx)


def test_volume_profile_shapes_and_volume_preserved():
    df = _ohlcv(20)
    centers, profile = _volume_profile(df, bins=10)
    # bins 경계는 10개 → 구간(centers/profile)은 9개
    assert len(centers) == 9
    assert len(profile) == 9
    # 모든 캔들의 거래량이 빠짐없이 분배되어 총합이 보존된다
    assert np.isclose(profile.sum(), df["Volume"].sum())
    # 가격대별 누적이므로 음수는 없다
    assert (profile >= 0).all()


def test_volume_profile_handles_flat_price():
    # High==Low로 가격 범위가 0이어도 예외 없이 동작
    df = pd.DataFrame({
        "Open": [100.0, 100.0], "High": [100.0, 100.0], "Low": [100.0, 100.0],
        "Close": [100.0, 100.0], "Volume": [1000.0, 2000.0]},
        index=pd.date_range("2024-01-01", periods=2, freq="D"))
    centers, profile = _volume_profile(df, bins=5)
    assert len(centers) == 4
    assert profile.sum() >= 0  # 예외 없이 반환


def test_generate_ta_chart_still_returns_png_with_volume_profile():
    png = generate_ta_chart(_ohlcv(), ticker="TEST", name="테스트종목", timeframe="DAILY")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1000


def test_default_prompt_mentions_volume_profile():
    assert "매물대" in DEFAULT_PROMPT
    assert "Volume Profile" in DEFAULT_PROMPT
