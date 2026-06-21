# 위험신호·매수매도 도움 (3단계 C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 보유 포트폴리오를 결정론적 규칙으로 스캔해 기술적·비중 위험신호를 일별 다이제스트 1건으로 텔레그램 발송하고, 설정·미리보기를 제공한다.

**Architecture:** 신규 `app/services/risk_signal/` 패키지(evaluator 순수규칙 → scanner 수집 → message 빌더 → risk_service 오케스트레이션). 기존 `chart_service.calculate_indicators`·`history_service`·`get_portfolio`·`schedules` 테이블·scheduler·telegram·settings_manager를 재사용한다. 신규 DB 테이블 없음.

**Tech Stack:** FastAPI + async SQLAlchemy 2.0 + asyncpg + PostgreSQL, pandas(지표), React 18 + Vite + TS. pytest(asyncio).

**테스트 실행 명령(공통):**
```bash
SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q
```
(순수함수 테스트는 DB 불필요하나 위 prefix를 붙여도 무해.)

---

## 파일 구조

**백엔드 (신규):**
- `app/services/risk_signal/__init__.py` (빈 파일)
- `app/services/risk_signal/evaluator.py` — 순수 규칙: `technical_signals`, `concentration_signals`
- `app/services/risk_signal/scanner.py` — 수집·오케스트레이션: `scan`
- `app/services/risk_signal/message.py` — `build_digest_message`
- `app/services/risk_signal/risk_service.py` — `load_config`, `build_digest`, `build_and_send`
- `app/routers/risk_signal.py` — `/api/risk-signal` 설정·스케줄·preview·send

**백엔드 (수정):**
- `app/services/scheduler/schedule_store.py` — `FEATURE_RISK` 상수
- `app/services/scheduler/handlers.py` — `handle_risk_signal` + 등록
- `app/main.py` — risk_signal 라우터 등록

**프론트 (수정):**
- `frontend/src/api.ts` — risk-signal 엔드포인트
- `frontend/src/pages/Settings.tsx` — "위험신호" 섹션

**테스트 (신규):**
- `tests/test_risk_evaluator.py`, `tests/test_risk_message.py`, `tests/test_risk_scanner.py`,
  `tests/test_risk_service.py`, `tests/test_risk_signal_api.py`, `tests/test_risk_signal_schedule.py`

---

## Task 1: evaluator 순수 규칙

**Files:**
- Create: `app/services/risk_signal/__init__.py` (빈 파일)
- Create: `app/services/risk_signal/evaluator.py`
- Test: `tests/test_risk_evaluator.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_risk_evaluator.py`:
```python
import pandas as pd
from app.services.risk_signal import evaluator as ev

_ALL_TECH = {"sig_rsi": True, "sig_macd": True, "sig_bollinger": True, "sig_ma": True}


def _df(rows: list[dict]) -> pd.DataFrame:
    # 최소 2행(직전/최신)을 가진 지표 DataFrame
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
    # 임계 미만은 미발동
    assert not any("애플" in s.get("name", "") for s in sigs)


def test_concentration_toggles_off():
    portfolio = {"positions": [{"ticker": "X", "name": "x", "weight_pct": 99.0}],
                 "allocation": [{"asset_class": "주식", "weight_pct": 99.0}]}
    cfg = {"sig_concentration_asset": False, "sig_concentration_class": False,
           "threshold_asset_pct": 30.0, "threshold_class_pct": 60.0}
    assert ev.concentration_signals(portfolio, cfg) == []
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_risk_evaluator.py -q`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: 구현**

`app/services/risk_signal/__init__.py` (빈 파일 생성).

`app/services/risk_signal/evaluator.py`:
```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_risk_evaluator.py -q`
Expected: PASS (전체)

- [ ] **Step 5: 커밋**
```bash
git add app/services/risk_signal/__init__.py app/services/risk_signal/evaluator.py tests/test_risk_evaluator.py
git commit -m "feat(risk): evaluator 순수 규칙(기술적·비중 신호)"
```

---

## Task 2: message 다이제스트 빌더

**Files:**
- Create: `app/services/risk_signal/message.py`
- Test: `tests/test_risk_message.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_risk_message.py`:
```python
from app.services.risk_signal import message as m


def test_empty_digest():
    out = m.build_digest_message([])
    assert "위험신호가 없습니다" in out


def test_digest_groups_sections():
    signals = [
        {"ticker": "005930", "name": "삼성", "category": "technical",
         "type": "RSI", "direction": "과매수", "detail": "73.2"},
        {"ticker": "005930", "name": "삼성", "category": "technical",
         "type": "MACD", "direction": "데드크로스", "detail": ""},
        {"category": "concentration", "type": "종목 과중", "name": "삼성(005930)", "detail": "62.0%"},
    ]
    out = m.build_digest_message(signals)
    assert "기술적 신호" in out and "비중 편향" in out
    assert "삼성" in out and "RSI" in out and "과매수" in out and "73.2" in out
    assert "데드크로스" in out
    assert "종목 과중" in out and "62.0%" in out
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_risk_message.py -q`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: 구현**

`app/services/risk_signal/message.py`:
```python
"""위험신호 목록 → 텔레그램 HTML 다이제스트(순수)."""

_HEADER = "<b>⚠️ 위험신호 다이제스트</b>"


def build_digest_message(signals: list[dict]) -> str:
    if not signals:
        return f"{_HEADER}\n\n현재 위험신호가 없습니다."
    tech = [s for s in signals if s["category"] == "technical"]
    conc = [s for s in signals if s["category"] == "concentration"]
    lines = [_HEADER]
    if tech:
        lines += ["", "[ 기술적 신호 ]"]
        for s in tech:
            detail = f" {s['detail']}" if s.get("detail") else ""
            lines.append(f"<b>{s['name']}</b> ({s['ticker']}): {s['type']} {s['direction']}{detail}")
    if conc:
        lines += ["", "[ 비중 편향 ]"]
        for s in conc:
            lines.append(f"{s['type']}: {s['name']} {s['detail']}")
    return "\n".join(lines)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_risk_message.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**
```bash
git add app/services/risk_signal/message.py tests/test_risk_message.py
git commit -m "feat(risk): 다이제스트 메시지 빌더"
```

---

## Task 3: scanner 수집·오케스트레이션

**Files:**
- Create: `app/services/risk_signal/scanner.py`
- Test: `tests/test_risk_scanner.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_risk_scanner.py`:
```python
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
    # calculate_indicators가 반환하는 형태의 최소 df(2행)
    return pd.DataFrame([
        {"RSI": 50, "MACD": 0, "Signal": 0, "Close": 10, "BB_upper": 99, "BB_lower": 1, "SMA50": 10},
        {"RSI": rsi_last, "MACD": 0, "Signal": 0, "Close": 10, "BB_upper": 99, "BB_lower": 1, "SMA50": 10},
    ])


@pytest.mark.asyncio
async def test_scan_collects_technical_and_concentration():
    raw = pd.DataFrame({"Close": [1, 2]})  # get_history 원본(형식만)
    with patch("app.services.risk_signal.scanner.get_portfolio", AsyncMock(return_value=_portfolio())), \
         patch("app.services.risk_signal.scanner.AsyncSessionGet", create=True), \
         patch("app.services.risk_signal.scanner.get_history", AsyncMock(return_value=raw)), \
         patch("app.services.risk_signal.scanner.calculate_indicators", return_value=_ind_df(75)):
        db = MagicMock()
        db.get = AsyncMock(return_value=MagicMock())  # asset 객체
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
    # 기술 신호는 없지만 비중 신호는 남아야 한다
    assert not any(s["category"] == "technical" for s in signals)
    assert any(s["category"] == "concentration" for s in signals)


@pytest.mark.asyncio
async def test_scan_skips_when_asset_missing():
    with patch("app.services.risk_signal.scanner.get_portfolio", AsyncMock(return_value=_portfolio())), \
         patch("app.services.risk_signal.scanner.get_history", AsyncMock(side_effect=AssertionError("불려선 안 됨"))):
        db = MagicMock()
        db.get = AsyncMock(return_value=None)   # asset 없음 → history 호출 안 함
        signals = await scanner.scan(db, _CFG)
    assert not any(s["category"] == "technical" for s in signals)
```

(참고: 위 `AsyncSessionGet` patch 줄은 사용하지 않으니 제거해도 된다 — 구현엔 불필요. 핵심은 `db.get` mock.)

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_risk_scanner.py -q`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: 구현**

`app/services/risk_signal/scanner.py`:
```python
"""보유 종목·포트폴리오를 스캔해 위험신호 목록을 만든다(수집+오케스트레이션)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset
from app.services.portfolio.portfolio_service import get_portfolio
from app.services.market.history_service import get_history
from app.services.chart.chart_service import calculate_indicators
from app.services.risk_signal import evaluator

_HISTORY_DAYS = 120   # SMA50 + MACD(26) 계산에 충분한 일봉


async def scan(db: AsyncSession, config: dict) -> list[dict]:
    """기술적(종목별) + 비중(전체) 신호를 모은 리스트. 시세 실패/무이력 종목은 기술 신호 스킵."""
    portfolio = await get_portfolio(db)
    signals: list[dict] = []

    tech_on = any(config.get(k) for k in ("sig_rsi", "sig_macd", "sig_bollinger", "sig_ma"))
    if tech_on:
        for p in portfolio["positions"]:
            asset = await db.get(Asset, p["asset_id"])
            if asset is None:
                continue
            try:
                df = await get_history(asset, _HISTORY_DAYS)
            except Exception:   # noqa: BLE001 — 한 종목 실패가 스캔 전체를 막지 않음
                df = None
            if df is None or len(df) < 2 or "Close" not in getattr(df, "columns", []):
                continue
            ind = calculate_indicators(df)
            signals.extend(evaluator.technical_signals(p["ticker"], p["name"], ind, config))

    signals.extend(evaluator.concentration_signals(portfolio, config))
    return signals
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_risk_scanner.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**
```bash
git add app/services/risk_signal/scanner.py tests/test_risk_scanner.py
git commit -m "feat(risk): scanner 수집·오케스트레이션"
```

---

## Task 4: risk_service (설정·다이제스트·발송)

**Files:**
- Create: `app/services/risk_signal/risk_service.py`
- Test: `tests/test_risk_service.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_risk_service.py`:
```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.risk_signal import risk_service as rs


def _settings(values: dict):
    async def fake(db, category, key):
        return values.get((category, key))
    return fake


@pytest.mark.asyncio
async def test_load_config_defaults_when_unset():
    with patch("app.services.risk_signal.risk_service.get_setting", _settings({})):
        cfg = await rs.load_config(MagicMock())
    assert cfg["enabled"] is False
    assert cfg["sig_rsi"] is True and cfg["sig_concentration_class"] is True
    assert cfg["threshold_asset_pct"] == 30.0 and cfg["threshold_class_pct"] == 60.0


@pytest.mark.asyncio
async def test_load_config_reads_stored_values():
    vals = {("risk_signal", "enabled"): "true", ("risk_signal", "sig_rsi"): "false",
            ("risk_signal", "threshold_asset_pct"): "25"}
    with patch("app.services.risk_signal.risk_service.get_setting", _settings(vals)):
        cfg = await rs.load_config(MagicMock())
    assert cfg["enabled"] is True and cfg["sig_rsi"] is False
    assert cfg["threshold_asset_pct"] == 25.0


@pytest.mark.asyncio
async def test_build_digest_uses_scanner_and_message():
    with patch("app.services.risk_signal.risk_service.load_config", AsyncMock(return_value={"x": 1})), \
         patch("app.services.risk_signal.risk_service.scanner.scan",
               AsyncMock(return_value=[{"category": "concentration", "type": "종목 과중",
                                        "name": "삼성(005930)", "detail": "62.0%"}])):
        out = await rs.build_digest(MagicMock())
    assert "비중 편향" in out and "종목 과중" in out


@pytest.mark.asyncio
async def test_build_and_send_calls_telegram():
    with patch("app.services.risk_signal.risk_service.build_digest", AsyncMock(return_value="msg")), \
         patch("app.services.risk_signal.risk_service.telegram_service.send_message",
               AsyncMock(return_value=True)) as sm:
        out = await rs.build_and_send(MagicMock())
    assert out["sent"] is True
    sm.assert_awaited_once()
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_risk_service.py -q`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: 구현**

`app/services/risk_signal/risk_service.py`:
```python
"""위험신호 설정 로드 + 다이제스트 생성/발송 오케스트레이션."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings.settings_manager import get_setting
from app.services.notification import telegram_service
from app.services.risk_signal import scanner, message

CATEGORY = "risk_signal"

_BOOL_DEFAULTS = {
    "enabled": False,
    "sig_rsi": True, "sig_macd": True, "sig_bollinger": True, "sig_ma": True,
    "sig_concentration_asset": True, "sig_concentration_class": True,
}
_FLOAT_DEFAULTS = {"threshold_asset_pct": 30.0, "threshold_class_pct": 60.0}


async def load_config(db: AsyncSession) -> dict:
    cfg: dict = {}
    for key, default in _BOOL_DEFAULTS.items():
        v = await get_setting(db, CATEGORY, key)
        cfg[key] = default if v is None else v.lower() == "true"
    for key, default in _FLOAT_DEFAULTS.items():
        v = await get_setting(db, CATEGORY, key)
        cfg[key] = default if v in (None, "") else float(v)
    return cfg


async def build_digest(db: AsyncSession) -> str:
    """현재 설정으로 스캔해 다이제스트 텍스트를 만든다(발송 안 함). 미리보기용."""
    cfg = await load_config(db)
    signals = await scanner.scan(db, cfg)
    return message.build_digest_message(signals)


async def build_and_send(db: AsyncSession) -> dict:
    """다이제스트를 만들어 텔레그램 발송. 미설정 시 TelegramNotConfigured 전파."""
    text = await build_digest(db)
    sent = await telegram_service.send_message(db, text)
    return {"sent": bool(sent)}
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_risk_service.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**
```bash
git add app/services/risk_signal/risk_service.py tests/test_risk_service.py
git commit -m "feat(risk): risk_service 설정·다이제스트·발송"
```

---

## Task 5: 스케줄 핸들러

**Files:**
- Modify: `app/services/scheduler/schedule_store.py`
- Modify: `app/services/scheduler/handlers.py`
- Test: `tests/test_risk_signal_schedule.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_risk_signal_schedule.py`:
```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.scheduler import handlers
from app.services.scheduler.schedule_store import FEATURE_RISK


def test_feature_risk_registered():
    assert FEATURE_RISK in handlers.HANDLERS


@pytest.mark.asyncio
async def test_handle_risk_signal_sends_when_enabled():
    sched = MagicMock(feature_type=FEATURE_RISK, target_id=0)
    with patch("app.services.scheduler.handlers.risk_service.load_config",
               AsyncMock(return_value={"enabled": True})), \
         patch("app.services.scheduler.handlers.risk_service.build_and_send",
               AsyncMock(return_value={"sent": True})) as bs:
        await handlers.handle_risk_signal(MagicMock(), sched)
    bs.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_risk_signal_skips_when_disabled():
    sched = MagicMock(feature_type=FEATURE_RISK, target_id=0)
    with patch("app.services.scheduler.handlers.risk_service.load_config",
               AsyncMock(return_value={"enabled": False})), \
         patch("app.services.scheduler.handlers.risk_service.build_and_send",
               AsyncMock(side_effect=AssertionError("발송되면 안 됨"))):
        await handlers.handle_risk_signal(MagicMock(), sched)   # 예외 없이 통과


@pytest.mark.asyncio
async def test_handle_risk_signal_swallows_telegram_not_configured():
    from app.services.notification import telegram_service
    sched = MagicMock(feature_type=FEATURE_RISK, target_id=0)
    with patch("app.services.scheduler.handlers.risk_service.load_config",
               AsyncMock(return_value={"enabled": True})), \
         patch("app.services.scheduler.handlers.risk_service.build_and_send",
               AsyncMock(side_effect=telegram_service.TelegramNotConfigured("no"))):
        await handlers.handle_risk_signal(MagicMock(), sched)   # 예외 없이 통과
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_risk_signal_schedule.py -q`
Expected: FAIL

- [ ] **Step 3: schedule_store 상수 추가**

`app/services/scheduler/schedule_store.py`의 FEATURE_* 상수 블록에 추가:
```python
FEATURE_RISK = "risk_signal"
```

- [ ] **Step 4: handlers 추가**

`app/services/scheduler/handlers.py`:
- import 추가:
```python
from app.services.risk_signal import risk_service
```
  그리고 기존 `from app.services.scheduler.schedule_store import ...` 줄에 `FEATURE_RISK` 추가.
- 핸들러 함수 추가(다른 핸들러 옆; `telegram_service`·`_log`는 이미 import됨 — 확인):
```python
async def handle_risk_signal(db: AsyncSession, schedule: Schedule) -> None:
    cfg = await risk_service.load_config(db)
    if not cfg["enabled"]:
        _log.info("위험신호 비활성 — 자동 발송 스킵")
        return
    try:
        await risk_service.build_and_send(db)
    except telegram_service.TelegramNotConfigured:
        _log.info("텔레그램 미설정 — 위험신호 발송 생략")
```
- HANDLERS dict에 등록:
```python
    FEATURE_RISK: handle_risk_signal,
```

- [ ] **Step 5: 통과 확인**

Run: `.venv/bin/pytest tests/test_risk_signal_schedule.py -q`
Expected: PASS

- [ ] **Step 6: 커밋**
```bash
git add app/services/scheduler/schedule_store.py app/services/scheduler/handlers.py tests/test_risk_signal_schedule.py
git commit -m "feat(risk): 스케줄 핸들러(handle_risk_signal)"
```

---

## Task 6: 라우터 (설정·스케줄·preview·send) + main 등록

**Files:**
- Create: `app/routers/risk_signal.py`
- Modify: `app/main.py`
- Test: `tests/test_risk_signal_api.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_risk_signal_api.py`:
```python
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.scheduler.schedule_store import FEATURE_RISK


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_get_settings():
    cfg = {"enabled": True, "sig_rsi": True, "threshold_asset_pct": 30.0}
    with patch("app.routers.risk_signal.risk_service.load_config", AsyncMock(return_value=cfg)):
        async with await _client() as ac:
            resp = await ac.get("/api/risk-signal/settings")
    assert resp.status_code == 200 and resp.json()["enabled"] is True


@pytest.mark.asyncio
async def test_put_settings():
    store = {}

    async def fake_set(db, cat, key, val, is_secret=False):
        store[(cat, key)] = val

    with patch("app.routers.risk_signal.set_setting", fake_set):
        async with await _client() as ac:
            resp = await ac.put("/api/risk-signal/settings",
                                json={"enabled": True, "sig_rsi": False, "threshold_asset_pct": 25})
    assert resp.status_code == 200
    assert store[("risk_signal", "enabled")] == "true"
    assert store[("risk_signal", "sig_rsi")] == "false"
    assert store[("risk_signal", "threshold_asset_pct")] == "25.0"


@pytest.mark.asyncio
async def test_preview_returns_text():
    with patch("app.routers.risk_signal.risk_service.build_digest",
               AsyncMock(return_value="다이제스트 텍스트")):
        async with await _client() as ac:
            resp = await ac.post("/api/risk-signal/preview")
    assert resp.status_code == 200 and resp.json()["text"] == "다이제스트 텍스트"


@pytest.mark.asyncio
async def test_send_409_when_telegram_not_configured():
    from app.services.notification import telegram_service
    with patch("app.routers.risk_signal.risk_service.build_and_send",
               AsyncMock(side_effect=telegram_service.TelegramNotConfigured("no"))):
        async with await _client() as ac:
            resp = await ac.post("/api/risk-signal/send")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_schedule_routes():
    from unittest.mock import MagicMock
    with patch("app.routers.risk_signal.schedule_store.upsert_schedule", AsyncMock()) as up, \
         patch("app.routers.risk_signal.schedule_store.get_schedule",
               AsyncMock(return_value=MagicMock(send_time="08:00", days_of_week="0,1,2,3,4", enabled=True))), \
         patch("app.routers.risk_signal.schedule_store.delete_schedule", AsyncMock()):
        async with await _client() as ac:
            put = await ac.put("/api/risk-signal/schedule",
                               json={"send_time": "08:00", "days_of_week": [0, 1, 2], "enabled": True})
            get = await ac.get("/api/risk-signal/schedule")
            dele = await ac.delete("/api/risk-signal/schedule")
    assert put.status_code == 200 and get.json()["send_time"] == "08:00" and dele.status_code == 200
    assert up.call_args.args[1] == FEATURE_RISK and up.call_args.args[2] == 0
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_risk_signal_api.py::test_get_settings -q`
Expected: FAIL (404)

- [ ] **Step 3: 라우터 구현**

`app/routers/risk_signal.py`:
```python
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.settings.settings_manager import set_setting
from app.services.risk_signal import risk_service
from app.services.scheduler import schedule_store
from app.services.scheduler.schedule_store import FEATURE_RISK
from app.services.notification import telegram_service

router = APIRouter(prefix="/api/risk-signal", tags=["risk-signal"])

CATEGORY = "risk_signal"
_BOOL_KEYS = ("enabled", "sig_rsi", "sig_macd", "sig_bollinger", "sig_ma",
              "sig_concentration_asset", "sig_concentration_class")
_FLOAT_KEYS = ("threshold_asset_pct", "threshold_class_pct")


class SettingsIn(BaseModel):
    enabled: bool | None = None
    sig_rsi: bool | None = None
    sig_macd: bool | None = None
    sig_bollinger: bool | None = None
    sig_ma: bool | None = None
    sig_concentration_asset: bool | None = None
    sig_concentration_class: bool | None = None
    threshold_asset_pct: float | None = None
    threshold_class_pct: float | None = None


class ScheduleIn(BaseModel):
    send_time: str
    days_of_week: list[int]
    enabled: bool = True

    @field_validator("send_time")
    @classmethod
    def _valid_time(cls, v: str) -> str:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("send_time은 HH:MM 형식이어야 합니다.")
        return v

    @field_validator("days_of_week")
    @classmethod
    def _valid_days(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("days_of_week는 0~6 정수여야 합니다.")
        return v


@router.get("/settings")
async def get_settings(db: AsyncSession = Depends(get_db)):
    return await risk_service.load_config(db)


@router.put("/settings")
async def put_settings(body: SettingsIn, db: AsyncSession = Depends(get_db)):
    for key in _BOOL_KEYS:
        v = getattr(body, key)
        if v is not None:
            await set_setting(db, CATEGORY, key, "true" if v else "false", is_secret=False)
    for key in _FLOAT_KEYS:
        v = getattr(body, key)
        if v is not None:
            await set_setting(db, CATEGORY, key, str(float(v)), is_secret=False)
    return {"status": "ok"}


@router.get("/schedule")
async def get_schedule(db: AsyncSession = Depends(get_db)):
    sched = await schedule_store.get_schedule(db, FEATURE_RISK, 0)
    if sched is None:
        return None
    return {"send_time": sched.send_time,
            "days_of_week": [int(x) for x in sched.days_of_week.split(",") if x != ""],
            "enabled": sched.enabled}


@router.put("/schedule")
async def put_schedule(body: ScheduleIn, db: AsyncSession = Depends(get_db)):
    days = ",".join(str(d) for d in sorted(set(body.days_of_week)))
    await schedule_store.upsert_schedule(db, FEATURE_RISK, 0, body.send_time, days, body.enabled)
    return {"status": "ok"}


@router.delete("/schedule")
async def delete_schedule(db: AsyncSession = Depends(get_db)):
    await schedule_store.delete_schedule(db, FEATURE_RISK, 0)
    return {"status": "ok"}


@router.post("/preview")
async def preview(db: AsyncSession = Depends(get_db)):
    return {"text": await risk_service.build_digest(db)}


@router.post("/send")
async def send(db: AsyncSession = Depends(get_db)):
    try:
        return await risk_service.build_and_send(db)
    except telegram_service.TelegramNotConfigured as e:
        raise HTTPException(409, str(e))
```

- [ ] **Step 4: main.py 등록**

`app/main.py`:
- import 줄에 `risk_signal` 추가(다른 라우터들과 함께).
- include_router 튜플에 `risk_signal.router` 추가.
Read 후 두 곳을 정확히 수정.

- [ ] **Step 5: 통과 확인**

Run: `.venv/bin/pytest tests/test_risk_signal_api.py -q`
Expected: PASS (전체)

- [ ] **Step 6: 커밋**
```bash
git add app/routers/risk_signal.py app/main.py tests/test_risk_signal_api.py
git commit -m "feat(risk): /api/risk-signal 라우터(설정·스케줄·preview·send) + 등록"
```

---

## Task 7: 프론트엔드 — 설정 "위험신호" 섹션

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: api.ts에 엔드포인트 추가**

`frontend/src/api.ts`의 `api` 객체에 추가:
```typescript
  getRiskSignal: () => j<{
    enabled: boolean; sig_rsi: boolean; sig_macd: boolean; sig_bollinger: boolean; sig_ma: boolean;
    sig_concentration_asset: boolean; sig_concentration_class: boolean;
    threshold_asset_pct: number; threshold_class_pct: number;
  }>("/api/risk-signal/settings"),
  saveRiskSignal: (s: Record<string, boolean | number>) =>
    j("/api/risk-signal/settings", { method: "PUT", body: JSON.stringify(s) }),
  getRiskSchedule: () =>
    j<{ send_time: string; days_of_week: number[]; enabled: boolean } | null>("/api/risk-signal/schedule"),
  saveRiskSchedule: (s: { send_time: string; days_of_week: number[]; enabled: boolean }) =>
    j("/api/risk-signal/schedule", { method: "PUT", body: JSON.stringify(s) }),
  previewRiskSignal: () => j<{ text: string }>("/api/risk-signal/preview", { method: "POST" }),
  sendRiskSignal: () => j<{ sent: boolean }>("/api/risk-signal/send", { method: "POST" }),
```

- [ ] **Step 2: Settings.tsx에 "위험신호" 섹션 추가**

기존 "AI 리포트" 섹션 패턴을 따라 추가한다. 상태:
```tsx
const [risk, setRisk] = useState({
  enabled: false, sig_rsi: true, sig_macd: true, sig_bollinger: true, sig_ma: true,
  sig_concentration_asset: true, sig_concentration_class: true,
  threshold_asset_pct: 30, threshold_class_pct: 60,
});
const [riskSched, setRiskSched] = useState({ send_time: "08:00", days_of_week: [0,1,2,3,4] as number[], enabled: false });
const [riskPreview, setRiskPreview] = useState("");
```
로딩(기존 useEffect 로더에 추가):
```tsx
api.getRiskSignal().then((r) => setRisk(r as any)).catch(() => {});
api.getRiskSchedule().then((s) => { if (s) setRiskSched(s); }).catch(() => {});
```
핸들러:
```tsx
const saveRisk = async () => { await api.saveRiskSignal(risk as any); };
const saveRiskSchedule = async () => { await api.saveRiskSchedule(riskSched); };
const doRiskPreview = async () => { const r = await api.previewRiskSignal(); setRiskPreview(r.text); };
const doRiskSend = async () => {
  try { await api.sendRiskSignal(); setRiskPreview("텔레그램으로 발송했습니다."); }
  catch (e) { setRiskPreview(String(e).includes("409") ? "텔레그램이 설정되지 않았습니다." : String(e)); }
};
```
JSX 섹션(클래스명은 기존 Settings.tsx에서 실제 쓰는 것 사용 — card/btn/btn-primary/input 등 확인):
```tsx
<section className="card space-y-3">
  <h2 className="font-semibold">위험신호</h2>
  <label className="flex items-center gap-2 text-sm">
    <input type="checkbox" checked={risk.enabled}
           onChange={(e) => setRisk({ ...risk, enabled: e.target.checked })} />
    자동 발송 활성화
  </label>

  <div className="space-y-1">
    <div className="text-sm font-semibold">기술적 신호</div>
    {([["sig_rsi","RSI 과매수/과매도"],["sig_macd","MACD 교차"],
       ["sig_bollinger","볼린저밴드 이탈"],["sig_ma","이동평균(SMA50) 돌파"]] as const).map(([k, label]) => (
      <label key={k} className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={(risk as any)[k]}
               onChange={(e) => setRisk({ ...risk, [k]: e.target.checked })} />
        {label}
      </label>
    ))}
  </div>

  <div className="space-y-2">
    <div className="text-sm font-semibold">비중 편향</div>
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={risk.sig_concentration_asset}
             onChange={(e) => setRisk({ ...risk, sig_concentration_asset: e.target.checked })} />
      단일 종목 과중 ≥
      <input className="input w-20" type="number" value={risk.threshold_asset_pct}
             onChange={(e) => setRisk({ ...risk, threshold_asset_pct: Number(e.target.value) })} /> %
    </label>
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={risk.sig_concentration_class}
             onChange={(e) => setRisk({ ...risk, sig_concentration_class: e.target.checked })} />
      단일 자산군 과중 ≥
      <input className="input w-20" type="number" value={risk.threshold_class_pct}
             onChange={(e) => setRisk({ ...risk, threshold_class_pct: Number(e.target.value) })} /> %
    </label>
  </div>

  <button className="btn btn-primary" onClick={saveRisk}>위험신호 설정 저장</button>

  <div className="border-t pt-3 space-y-2" style={{ borderColor: "var(--border)" }}>
    <h3 className="text-sm font-semibold">자동 발송 스케줄</h3>
    <label className="block text-sm">발송 시각(KST)
      <input className="input" type="time" value={riskSched.send_time}
             onChange={(e) => setRiskSched({ ...riskSched, send_time: e.target.value })} />
    </label>
    <div className="flex flex-wrap gap-2 text-sm">
      {["월","화","수","목","금","토","일"].map((d, i) => (
        <label key={i} className="flex items-center gap-1">
          <input type="checkbox" checked={riskSched.days_of_week.includes(i)}
                 onChange={(e) => setRiskSched({
                   ...riskSched,
                   days_of_week: e.target.checked
                     ? [...riskSched.days_of_week, i]
                     : riskSched.days_of_week.filter((x) => x !== i),
                 })} />
          {d}
        </label>
      ))}
    </div>
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={riskSched.enabled}
             onChange={(e) => setRiskSched({ ...riskSched, enabled: e.target.checked })} />
      스케줄 사용
    </label>
    <button className="btn btn-primary" onClick={saveRiskSchedule}>스케줄 저장</button>
  </div>

  <div className="flex gap-2">
    <button className="btn" onClick={doRiskPreview}>지금 미리보기</button>
    <button className="btn" onClick={doRiskSend}>지금 보내기</button>
  </div>
  {riskPreview && <div className="card whitespace-pre-wrap text-sm">{riskPreview}</div>}
</section>
```
> 참고: 미리보기 텍스트는 텔레그램 HTML(`<b>` 등)이 섞일 수 있다. 화면 표시는 단순 텍스트로 충분(태그가 보여도 동작엔 무해). 깔끔하게 하려면 후속에 태그 제거 가능 — v1 비목표.

- [ ] **Step 3: 빌드·타입체크**

Run: `cd frontend && npm run build`
Expected: 성공(타입 에러 0). 실패 시 클래스명/타입 수정.

- [ ] **Step 4: 커밋**
```bash
git add frontend/src/api.ts frontend/src/pages/Settings.tsx
git commit -m "feat(risk): 위험신호 설정 섹션(프론트)"
```

---

## Task 8: 최종 검증 + 로드맵

**Files:**
- Modify: `docs/superpowers/ROADMAP.md`

- [ ] **Step 1: 백엔드 전체 테스트**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q`
Expected: 전부 PASS(기존 207 + 신규 약 24 = 약 231). 실패 0.

- [ ] **Step 2: 프론트 빌드**

Run: `cd frontend && npm run build`
Expected: 성공.

- [ ] **Step 3: ROADMAP에 3단계 C 완료 항목 추가**

`docs/superpowers/ROADMAP.md`의 "### 3단계 C/D — 미착수" 섹션에서 C를 별도 "구현 완료" 항목으로 옮기고 spec/plan 경로·테스트 수·"실 텔레그램 스모크 사용자 확인"을 기록. D는 미착수로 유지. 상단 헤더 "(A·B 완료)"를 "(A·B·C 완료)"로 갱신.

- [ ] **Step 4: 커밋**
```bash
git add docs/superpowers/ROADMAP.md
git commit -m "docs(roadmap): 3단계 C 위험신호 완료 반영"
```

> **실 스모크(사용자 확인 대기)**: 설정에서 위험신호 활성화·신호/임계값·스케줄 입력 → "지금 미리보기"로 현재 보유 스캔 결과 확인 → "지금 보내기"로 텔레그램 확인 → 스케줄 자동 발송 확인.

---

## Self-Review (작성자 확인 완료)

- **스펙 커버리지**: 규칙기반 결정론(LLM 없음)=evaluator(T1) / 기술 4신호 on-off=evaluator+config(T1) / 비중 2신호 on-off+임계값=evaluator(T1)·settings(T4·T6) / 일별 다이제스트=message(T2)+scanner(T3) / 보유 전체 자동·manual 스킵=scanner(T3) / 설정·스케줄·preview·send API=router(T6) / 스케줄 재사용·best-effort·enabled 게이팅=handler(T5) / 프론트 설정 섹션=‌(T7) / 에러처리(미설정 409·시세실패 스킵·0건)=T3·T4·T6. 모두 매핑됨.
- **플레이스홀더**: 없음(모든 코드 실내용).
- **타입 일관성**: `technical_signals(ticker,name,df,config)`/`concentration_signals(portfolio,config)`/`scanner.scan(db,config)`/`build_digest(db)`/`build_and_send(db)->{"sent":bool}`/`load_config(db)->dict`/`FEATURE_RISK`/신호 dict 키(category/type/direction/detail/name/ticker)가 정의처·소비처(message·scanner·router·handler) 전반에서 일치. settings 키 집합(_BOOL_DEFAULTS/_FLOAT_DEFAULTS ↔ router _BOOL_KEYS/_FLOAT_KEYS ↔ 프론트 필드) 일치.
