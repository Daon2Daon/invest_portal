import pandas as pd
from app.services.risk_signal import evaluator as ev

_ALL_TECH = {"sig_rsi": True, "sig_macd": True, "sig_bollinger": True, "sig_ma": True}


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_rsi_overbought_and_oversold():
    over = _df([{"RSI": 50, "MACD": 0, "Signal": 0, "Close": 10, "BB_upper": 99, "BB_lower": 1, "SMA50": 10},
                {"RSI": 75, "MACD": 0, "Signal": 0, "Close": 10, "BB_upper": 99, "BB_lower": 1, "SMA50": 10}])
    sigs = ev.technical_signals("005930", "삼성", over, _ALL_TECH)
    assert any(s["type"] == "RSI" and s["direction"] == "과매수" for s in sigs)
    under = over.copy(); under.loc[1, "RSI"] = 25
    sigs = ev.technical_signals("005930", "삼성", under, _ALL_TECH)
    assert any(s["type"] == "RSI" and s["direction"] == "과매도" for s in sigs)


def test_rsi_neutral_no_signal():
    neutral = _df([{"RSI": 50, "MACD": 0, "Signal": 0, "Close": 10, "BB_upper": 99, "BB_lower": 1, "SMA50": 10},
                   {"RSI": 55, "MACD": 0, "Signal": 0, "Close": 10, "BB_upper": 99, "BB_lower": 1, "SMA50": 10}])
    assert ev.technical_signals("X", "x", neutral, _ALL_TECH) == []


def test_macd_golden_and_dead_cross():
    golden = _df([{"RSI": 50, "MACD": -1, "Signal": 0, "Close": 10, "BB_upper": 99, "BB_lower": 1, "SMA50": 10},
                  {"RSI": 50, "MACD": 1, "Signal": 0, "Close": 10, "BB_upper": 99, "BB_lower": 1, "SMA50": 10}])
    assert any(s["type"] == "MACD" and s["direction"] == "골든크로스"
               for s in ev.technical_signals("X", "x", golden, _ALL_TECH))
    dead = _df([{"RSI": 50, "MACD": 1, "Signal": 0, "Close": 10, "BB_upper": 99, "BB_lower": 1, "SMA50": 10},
                {"RSI": 50, "MACD": -1, "Signal": 0, "Close": 10, "BB_upper": 99, "BB_lower": 1, "SMA50": 10}])
    assert any(s["type"] == "MACD" and s["direction"] == "데드크로스"
               for s in ev.technical_signals("X", "x", dead, _ALL_TECH))


def test_bollinger_breaks():
    up = _df([{"RSI": 50, "MACD": 0, "Signal": 0, "Close": 10, "BB_upper": 12, "BB_lower": 8, "SMA50": 10},
              {"RSI": 50, "MACD": 0, "Signal": 0, "Close": 13, "BB_upper": 12, "BB_lower": 8, "SMA50": 10}])
    assert any(s["type"] == "볼린저" and s["direction"] == "상단 이탈"
               for s in ev.technical_signals("X", "x", up, _ALL_TECH))
    down = up.copy(); down.loc[1, "Close"] = 7
    assert any(s["type"] == "볼린저" and s["direction"] == "하단 이탈"
               for s in ev.technical_signals("X", "x", down, _ALL_TECH))


def test_ma_cross():
    up = _df([{"RSI": 50, "MACD": 0, "Signal": 0, "Close": 9, "BB_upper": 99, "BB_lower": 1, "SMA50": 10},
              {"RSI": 50, "MACD": 0, "Signal": 0, "Close": 11, "BB_upper": 99, "BB_lower": 1, "SMA50": 10}])
    assert any(s["type"] == "SMA50" and s["direction"] == "상향 돌파"
               for s in ev.technical_signals("X", "x", up, _ALL_TECH))
    down = _df([{"RSI": 50, "MACD": 0, "Signal": 0, "Close": 11, "BB_upper": 99, "BB_lower": 1, "SMA50": 10},
                {"RSI": 50, "MACD": 0, "Signal": 0, "Close": 9, "BB_upper": 99, "BB_lower": 1, "SMA50": 10}])
    assert any(s["type"] == "SMA50" and s["direction"] == "하향 돌파"
               for s in ev.technical_signals("X", "x", down, _ALL_TECH))


def test_toggles_off_suppress_signals():
    over = _df([{"RSI": 50, "MACD": -1, "Signal": 0, "Close": 13, "BB_upper": 12, "BB_lower": 8, "SMA50": 10},
                {"RSI": 75, "MACD": 1, "Signal": 0, "Close": 13, "BB_upper": 12, "BB_lower": 8, "SMA50": 10}])
    off = {"sig_rsi": False, "sig_macd": False, "sig_bollinger": False, "sig_ma": False}
    assert ev.technical_signals("X", "x", over, off) == []


def test_nan_indicator_skipped():
    nan_rsi = _df([{"RSI": 50, "MACD": 0, "Signal": 0, "Close": 10, "BB_upper": 99, "BB_lower": 1, "SMA50": 10},
                   {"RSI": float("nan"), "MACD": 0, "Signal": 0, "Close": 10, "BB_upper": 99, "BB_lower": 1, "SMA50": 10}])
    assert not any(s["type"] == "RSI" for s in ev.technical_signals("X", "x", nan_rsi, _ALL_TECH))


def test_concentration_signals():
    portfolio = {
        "positions": [{"ticker": "005930", "name": "삼성", "weight_pct": 62.0},
                      {"ticker": "AAPL", "name": "애플", "weight_pct": 10.0}],
        "allocation": [{"asset_class": "주식", "weight_pct": 70.0},
                       {"asset_class": "현금성", "weight_pct": 30.0}],
    }
    cfg = {"sig_concentration_asset": True, "sig_concentration_class": True,
           "threshold_asset_pct": 30.0, "threshold_class_pct": 60.0}
    sigs = ev.concentration_signals(portfolio, cfg)
    assert any(s["type"] == "종목 과중" and "삼성" in s["name"] for s in sigs)
    assert any(s["type"] == "자산군 과중" and s["name"] == "주식" for s in sigs)
    assert not any("애플" in s.get("name", "") for s in sigs)


def test_concentration_toggles_off():
    portfolio = {"positions": [{"ticker": "X", "name": "x", "weight_pct": 99.0}],
                 "allocation": [{"asset_class": "주식", "weight_pct": 99.0}]}
    cfg = {"sig_concentration_asset": False, "sig_concentration_class": False,
           "threshold_asset_pct": 30.0, "threshold_class_pct": 60.0}
    assert ev.concentration_signals(portfolio, cfg) == []
