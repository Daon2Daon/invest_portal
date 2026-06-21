"""위험신호 순수 규칙(네트워크/DB 없음). 기술적: 지표 DataFrame, 비중: 포트폴리오 dict."""
from __future__ import annotations

import pandas as pd


def technical_signals(ticker: str, name: str, df: pd.DataFrame, config: dict) -> list[dict]:
    """지표가 계산된 일봉 DataFrame(최신·직전 봉)으로 기술적 신호 목록을 만든다.

    df 필요 컬럼: RSI, MACD, Signal, Close, BB_upper, BB_lower, SMA50.
    NaN(이력 부족)인 지표의 신호는 건너뛴다. df는 2행 이상이어야 한다(호출측 보장).
    """
    out: list[dict] = []
    last = df.iloc[-1]
    prev = df.iloc[-2]

    def _ok(*cols) -> bool:
        return all(not pd.isna(last[c]) for c in cols)

    def _ok_prev(*cols) -> bool:
        return all(not pd.isna(prev[c]) for c in cols)

    def sig(type_: str, direction: str, detail: str) -> None:
        out.append({"ticker": ticker, "name": name, "category": "technical",
                    "type": type_, "direction": direction, "detail": detail})

    if config.get("sig_rsi") and _ok("RSI"):
        rsi = float(last["RSI"])
        if rsi >= 70:
            sig("RSI", "과매수", f"{rsi:.1f}")
        elif rsi <= 30:
            sig("RSI", "과매도", f"{rsi:.1f}")

    if config.get("sig_macd") and _ok("MACD", "Signal") and _ok_prev("MACD", "Signal"):
        prev_diff = float(prev["MACD"]) - float(prev["Signal"])
        last_diff = float(last["MACD"]) - float(last["Signal"])
        if prev_diff <= 0 and last_diff > 0:
            sig("MACD", "골든크로스", "")
        elif prev_diff >= 0 and last_diff < 0:
            sig("MACD", "데드크로스", "")

    if config.get("sig_bollinger") and _ok("Close", "BB_upper", "BB_lower"):
        c = float(last["Close"])
        if c > float(last["BB_upper"]):
            sig("볼린저", "상단 이탈", f"{c:.2f}")
        elif c < float(last["BB_lower"]):
            sig("볼린저", "하단 이탈", f"{c:.2f}")

    if config.get("sig_ma") and _ok("Close", "SMA50") and _ok_prev("Close", "SMA50"):
        pc, ps = float(prev["Close"]), float(prev["SMA50"])
        lc, ls = float(last["Close"]), float(last["SMA50"])
        if pc <= ps and lc > ls:
            sig("SMA50", "상향 돌파", f"{lc:.2f}")
        elif pc >= ps and lc < ls:
            sig("SMA50", "하향 돌파", f"{lc:.2f}")

    return out


def concentration_signals(portfolio: dict, config: dict) -> list[dict]:
    """포트폴리오 비중 편향(단일 종목/자산군 과중) 신호 목록."""
    out: list[dict] = []
    if config.get("sig_concentration_asset"):
        thr = float(config.get("threshold_asset_pct", 30.0))
        for p in portfolio["positions"]:
            if p["weight_pct"] >= thr:
                out.append({"category": "concentration", "type": "종목 과중",
                            "name": f'{p["name"]}({p["ticker"]})',
                            "detail": f'{p["weight_pct"]:.1f}%'})
    if config.get("sig_concentration_class"):
        thr = float(config.get("threshold_class_pct", 60.0))
        for a in portfolio["allocation"]:
            if a["weight_pct"] >= thr:
                out.append({"category": "concentration", "type": "자산군 과중",
                            "name": a["asset_class"], "detail": f'{a["weight_pct"]:.1f}%'})
    return out
