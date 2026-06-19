# 증시 마감 요약 푸시 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** US·KR 증시 마감 시각에 지수 + 보유/관심 종목의 일·주·월 변동·52주 고점대비를 텔레그램으로 요약 발송한다.

**Architecture:** 기존 `schedules` 테이블·1분 tick 디스패처를 시장별 `feature_type`로 재사용(신규 테이블 없음). 콘텐츠는 신규 `services/market_summary/`(indices·changes·message·summary_service)가 `history_service`/yfinance로 구성하고, `market_hours.is_trading_day`로 휴장일을 스킵한다. 설정 UI는 설정 페이지의 증시 요약 섹션.

**Tech Stack:** FastAPI + async SQLAlchemy(asyncpg/PostgreSQL), APScheduler, pandas_market_calendars, yfinance, pytest/httpx, React 19 + TS/Vite.

설계 spec: `docs/superpowers/specs/2026-06-20-market-summary-push-design.md`

---

## 파일 구조

신규
- `app/services/market_summary/__init__.py` (빈 패키지)
- `app/services/market_summary/changes.py` — `asset_stats`
- `app/services/market_summary/indices.py` — `INDICES`, `index_lines`
- `app/services/market_summary/message.py` — `build_message`
- `app/services/market_summary/summary_service.py` — `build_and_send`
- `app/routers/market_summary.py` — `/api/market-summary`
- `tests/test_summary_changes.py`, `test_summary_indices.py`, `test_summary_message.py`, `test_summary_service.py`, `test_market_summary_api.py`

수정
- `app/services/market/market_hours.py` — `_MARKET_TZ` + `is_trading_day`
- `app/services/scheduler/schedule_store.py` — `FEATURE_SUMMARY_US/KR` 상수
- `app/services/scheduler/handlers.py` — `handle_market_summary` + 레지스트리 2개
- `app/main.py` — market_summary 라우터 등록
- `tests/test_market_hours.py` — is_trading_day 테스트 추가
- `frontend/src/api.ts`, `frontend/src/pages/Settings.tsx`

> 모든 명령은 venv로: `.venv/bin/pytest ...`, `.venv/bin/python ...`. DB 통합 테스트는 다음에서만 실제 실행(미설정 시 skip):
> `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db'`

---

### Task 1: 거래일 체크 `is_trading_day`

**Files:**
- Modify: `app/services/market/market_hours.py`
- Test: `tests/test_market_hours.py` (기존 파일에 추가)

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_market_hours.py` 끝에 추가:

```python
from app.services.market.market_hours import is_trading_day


def test_is_trading_day_weekday_true():
    # 2026-06-17(수) — NYSE/XKRX 모두 거래일
    assert is_trading_day("US", _utc(2026, 6, 17, 15, 0)) is True
    assert is_trading_day("KR", _utc(2026, 6, 17, 1, 0)) is True


def test_is_trading_day_weekend_false():
    # 2026-06-20(토)
    assert is_trading_day("US", _utc(2026, 6, 20, 15, 0)) is False
    assert is_trading_day("KR", _utc(2026, 6, 20, 1, 0)) is False


def test_is_trading_day_crypto_and_unknown_true():
    assert is_trading_day("CRYPTO", _utc(2026, 6, 20, 0, 0)) is True
    assert is_trading_day("XX", _utc(2026, 6, 20, 0, 0)) is True
```

(`_utc` 헬퍼는 이 파일 상단에 이미 정의되어 있다.)

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_market_hours.py -k is_trading_day -v`
Expected: FAIL — `ImportError: cannot import name 'is_trading_day'`

- [ ] **Step 3: 구현**

`app/services/market/market_hours.py` 상단 import에 `ZoneInfo` 추가:

```python
from zoneinfo import ZoneInfo
```

`_CAL_NAMES` 아래에 추가:

```python
_MARKET_TZ = {"US": "America/New_York", "KR": "Asia/Seoul", "JP": "Asia/Tokyo"}
```

파일 끝에 함수 추가:

```python
def is_trading_day(market: str, now: datetime) -> bool:
    """해당 시장의 now(시장 tz 환산) 날짜가 거래일인지. CRYPTO/미지/오류 → True(fail-open)."""
    if market == "CRYPTO":
        return True
    name = _CAL_NAMES.get(market)
    tzname = _MARKET_TZ.get(market)
    if name is None or tzname is None:
        return True
    try:
        cal = _calendar(name)
        d = now.astimezone(ZoneInfo(tzname)).date().isoformat()
        sched = cal.schedule(start_date=d, end_date=d)
        return not sched.empty
    except Exception:
        return True
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_market_hours.py -v`
Expected: PASS (기존 8 + 신규 3)

- [ ] **Step 5: 커밋**

```bash
git add app/services/market/market_hours.py tests/test_market_hours.py
git commit -m "feat(summary): market_hours.is_trading_day"
```

---

### Task 2: 종목 통계 `changes.asset_stats`

**Files:**
- Create: `app/services/market_summary/__init__.py` (빈 파일)
- Create: `app/services/market_summary/changes.py`
- Test: `tests/test_summary_changes.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_summary_changes.py` 생성:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_summary_changes.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.market_summary.changes`

- [ ] **Step 3: 구현**

`app/services/market_summary/__init__.py` 생성(빈 파일).

`app/services/market_summary/changes.py` 생성:

```python
"""종목 통계: 일·주·월 변동률 + 52주 고점/고점대비. history_service 사용."""
from app.services.market.history_service import get_history


async def asset_stats(asset) -> dict | None:
    df = await get_history(asset, 370)
    if df is None or len(df) < 2:
        return None
    close = df["Close"]
    current = float(close.iloc[-1])

    def pct(n: int):
        if len(close) <= n:
            return None
        prev = float(close.iloc[-1 - n])
        return (current - prev) / prev * 100 if prev else None

    wk52_high = float(df["High"].max())
    drop = (current - wk52_high) / wk52_high * 100 if wk52_high else 0.0
    return {
        "current": current,
        "daily_pct": pct(1), "weekly_pct": pct(5), "monthly_pct": pct(21),
        "wk52_high": wk52_high, "wk52_drop_pct": drop,
    }
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_summary_changes.py -v`
Expected: PASS (2개)

- [ ] **Step 5: 커밋**

```bash
git add app/services/market_summary/__init__.py app/services/market_summary/changes.py tests/test_summary_changes.py
git commit -m "feat(summary): asset_stats(일/주/월·52주)"
```

---

### Task 3: 지수 조회 `indices.index_lines`

**Files:**
- Create: `app/services/market_summary/indices.py`
- Test: `tests/test_summary_indices.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_summary_indices.py` 생성:

```python
import pytest
from unittest.mock import patch

from app.services.market_summary.indices import index_lines, INDICES


def test_indices_map_has_us_kr():
    assert [s for s, _ in INDICES["US"]] == ["^GSPC", "^IXIC", "^DJI"]
    assert [s for s, _ in INDICES["KR"]] == ["^KS11", "^KQ11"]


@pytest.mark.asyncio
async def test_index_lines_skips_failed():
    def fake_fetch(symbol):
        if symbol == "^IXIC":
            return None  # 실패 지수
        return (100.0, 1.5)
    with patch("app.services.market_summary.indices._fetch", side_effect=fake_fetch):
        rows = await index_lines("US")
    names = [r["name"] for r in rows]
    assert "NASDAQ" not in names          # 실패 지수 제외
    assert rows[0]["price"] == 100.0
    assert rows[0]["change_pct"] == 1.5
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_summary_indices.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.market_summary.indices`

- [ ] **Step 3: 구현**

`app/services/market_summary/indices.py` 생성:

```python
"""주요 지수 현재가·전일대비%. 지수는 DB 자산이 아니라 yfinance 직접 조회."""
import asyncio

import yfinance as yf

from app.services.market._num import finite

INDICES = {
    "US": [("^GSPC", "S&P 500"), ("^IXIC", "NASDAQ"), ("^DJI", "다우")],
    "KR": [("^KS11", "KOSPI"), ("^KQ11", "KOSDAQ")],
}


def _fetch(symbol: str):
    """(price, change_pct) 또는 None(실패)."""
    try:
        hist = yf.Ticker(symbol).history(period="5d")
    except Exception:
        return None
    if hist is None or hist.empty:
        return None
    close = hist["Close"]
    price = finite(close.iloc[-1])
    if price is None:
        return None
    chg = None
    if len(close) >= 2:
        prev = finite(close.iloc[-2])
        if prev:
            chg = (price - prev) / prev * 100
    return price, chg


async def index_lines(market: str) -> list[dict]:
    out: list[dict] = []
    for symbol, name in INDICES.get(market, []):
        r = await asyncio.to_thread(_fetch, symbol)
        if r is None:
            continue
        price, chg = r
        out.append({"name": name, "price": price, "change_pct": chg})
    return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_summary_indices.py -v`
Expected: PASS (2개)

- [ ] **Step 5: 커밋**

```bash
git add app/services/market_summary/indices.py tests/test_summary_indices.py
git commit -m "feat(summary): 지수 조회 index_lines"
```

---

### Task 4: 메시지 빌더 `message.build_message`

**Files:**
- Create: `app/services/market_summary/message.py`
- Test: `tests/test_summary_message.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_summary_message.py` 생성:

```python
from app.services.market_summary.message import build_message


def _stats(current, d, w, m, drop):
    return {"current": current, "daily_pct": d, "weekly_pct": w,
            "monthly_pct": m, "wk52_high": current * 1.2, "wk52_drop_pct": drop}


def test_message_kr_holdings_and_index():
    indices = [{"name": "KOSPI", "price": 2800.12, "change_pct": 1.23}]
    holdings = [("삼성전자", "005930", _stats(59500.0, 1.0, -2.0, 3.0, -8.5))]
    msg = build_message("KR", indices, holdings, [])
    assert "한국 증시 마감 요약" in msg
    assert "KOSPI" in msg and "2,800" in msg
    assert "삼성전자" in msg and "59,500원" in msg
    assert "📈" in msg or "📉" in msg
    assert "52주 고점대비" in msg


def test_message_us_watchlist_dollar_and_none_pct():
    indices = [{"name": "S&P 500", "price": 5000.0, "change_pct": None}]
    watch = [("Tesla", "TSLA", _stats(250.0, None, 1.0, 2.0, -5.0))]
    msg = build_message("US", indices, [], watch)
    assert "$250.00" in msg
    assert "관심 종목" in msg
    assert "—" in msg  # daily_pct None → —
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_summary_message.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.market_summary.message`

- [ ] **Step 3: 구현**

`app/services/market_summary/message.py` 생성:

```python
"""증시 요약 텔레그램 HTML 메시지 빌더(순수). 통화: KR=원(정수), US=$(소수2)."""

_TITLE = {"US": "미국 증시", "KR": "한국 증시"}


def _fmt(price: float, market: str) -> str:
    if market == "KR":
        return f"{price:,.0f}원"
    return f"${price:,.2f}"


def _sign(pct) -> str:
    if pct is None:
        return "—"
    arrow = "📈" if pct >= 0 else "📉"
    return f"{arrow}{pct:+.2f}%"


def build_message(market: str, indices: list[dict],
                  holdings_stats: list[tuple], watchlist_stats: list[tuple]) -> str:
    """holdings_stats/watchlist_stats: [(name, ticker, stats_dict), ...]."""
    lines = [f"<b>📊 {_TITLE.get(market, market)} 마감 요약</b>", "", "[ 주요 지수 ]"]
    for ix in indices:
        lines.append(f"{ix['name']}: {ix['price']:,.2f} ({_sign(ix['change_pct'])})")
    for title, rows in (("보유 종목", holdings_stats), ("관심 종목", watchlist_stats)):
        if not rows:
            continue
        lines.append("")
        lines.append(f"[ {title} ]")
        for name, ticker, s in rows:
            lines.append(f"<b>{name}</b> ({ticker})")
            lines.append(f"  {_fmt(s['current'], market)} | "
                         f"일{_sign(s['daily_pct'])} 주{_sign(s['weekly_pct'])} 월{_sign(s['monthly_pct'])}")
            lines.append(f"  52주 고점대비 {s['wk52_drop_pct']:+.1f}%")
    return "\n".join(lines)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_summary_message.py -v`
Expected: PASS (2개)

- [ ] **Step 5: 커밋**

```bash
git add app/services/market_summary/message.py tests/test_summary_message.py
git commit -m "feat(summary): 텔레그램 메시지 빌더"
```

---

### Task 5: 조립·발송 `summary_service.build_and_send`

**Files:**
- Create: `app/services/market_summary/summary_service.py`
- Test: `tests/test_summary_service.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_summary_service.py` 생성:

```python
import pytest
from unittest.mock import patch, AsyncMock

from app.models import Asset, Holding
from app.services.market_summary import summary_service


def _asset(**kw):
    base = dict(ticker="T", name="N", asset_type="stock", market="US",
                currency="USD", data_source="yfinance", fetch_symbol="T")
    base.update(kw)
    return Asset(**base)


@pytest.mark.asyncio
async def test_build_and_send_filters_market_and_classifies(db_session):
    us_held = _asset(ticker="AAPL", fetch_symbol="AAPL", market="US")
    us_watch = _asset(ticker="TSLA", fetch_symbol="TSLA", market="US")
    kr = _asset(ticker="005930", fetch_symbol="005930", market="KR")
    db_session.add_all([us_held, us_watch, kr])
    await db_session.commit()
    db_session.add(Holding(asset_id=us_held.asset_id, quantity=1, purchase_price=10, fee=0))
    await db_session.commit()

    stats = {"current": 100.0, "daily_pct": 1.0, "weekly_pct": 2.0,
             "monthly_pct": 3.0, "wk52_high": 120.0, "wk52_drop_pct": -16.7}
    sent = AsyncMock(return_value=True)
    with patch("app.services.market_summary.summary_service.index_lines",
               AsyncMock(return_value=[{"name": "S&P 500", "price": 5000.0, "change_pct": 1.0}])), \
         patch("app.services.market_summary.summary_service.asset_stats", AsyncMock(return_value=stats)), \
         patch("app.services.market_summary.summary_service.telegram_service.send_message", sent):
        res = await summary_service.build_and_send(db_session, "US")

    assert res["market"] == "US"
    assert res["holdings"] == 1     # AAPL
    assert res["watchlist"] == 1    # TSLA (KR 제외)
    assert res["sent"] is True
    sent.assert_awaited_once()
    msg = sent.await_args.args[1]
    assert "AAPL" in msg and "TSLA" in msg and "005930" not in msg


@pytest.mark.asyncio
async def test_build_and_send_skips_assets_without_stats(db_session):
    a = _asset(ticker="NOHIST", fetch_symbol="NOHIST", market="US")
    db_session.add(a); await db_session.commit()
    with patch("app.services.market_summary.summary_service.index_lines", AsyncMock(return_value=[])), \
         patch("app.services.market_summary.summary_service.asset_stats", AsyncMock(return_value=None)), \
         patch("app.services.market_summary.summary_service.telegram_service.send_message", AsyncMock(return_value=True)):
        res = await summary_service.build_and_send(db_session, "US")
    assert res["holdings"] == 0 and res["watchlist"] == 0
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_summary_service.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.market_summary.summary_service`

- [ ] **Step 3: 구현**

`app/services/market_summary/summary_service.py` 생성:

```python
"""지수 + 그 시장 보유/관심 종목 통계를 모아 텔레그램으로 발송."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset
from app.services.portfolio.portfolio_service import held_asset_ids
from app.services.market_summary.indices import index_lines
from app.services.market_summary.changes import asset_stats
from app.services.market_summary.message import build_message
from app.services.notification import telegram_service


async def build_and_send(db: AsyncSession, market: str) -> dict:
    indices = await index_lines(market)
    held = await held_asset_ids(db)
    assets = (await db.execute(
        select(Asset).where(Asset.is_active == True, Asset.market == market)  # noqa: E712
    )).scalars().all()
    holdings, watch = [], []
    for a in assets:
        s = await asset_stats(a)
        if s is None:
            continue
        row = (a.name, a.ticker, s)
        (holdings if a.asset_id in held else watch).append(row)
    msg = build_message(market, indices, holdings, watch)
    sent = await telegram_service.send_message(db, msg)
    return {"market": market, "sent": bool(sent),
            "indices": len(indices), "holdings": len(holdings), "watchlist": len(watch)}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_summary_service.py -v`
Expected: PASS (2개) 또는 SKIP(TEST_DATABASE_URL 미설정)

- [ ] **Step 5: 커밋**

```bash
git add app/services/market_summary/summary_service.py tests/test_summary_service.py
git commit -m "feat(summary): build_and_send(시장 필터·분류·발송)"
```

---

### Task 6: 스케줄 상수 + 핸들러 등록

**Files:**
- Modify: `app/services/scheduler/schedule_store.py`
- Modify: `app/services/scheduler/handlers.py`
- Test: `tests/test_summary_service.py` (핸들러 테스트 추가)

- [ ] **Step 1: 실패하는 핸들러 테스트 추가**

`tests/test_summary_service.py` 끝에 추가:

```python
from unittest.mock import MagicMock
import app.services.scheduler.handlers as handlers
from app.services.scheduler.schedule_store import FEATURE_SUMMARY_US


@pytest.mark.asyncio
async def test_handler_skips_on_holiday():
    sched = MagicMock(feature_type=FEATURE_SUMMARY_US)
    bsend = AsyncMock()
    with patch.object(handlers, "is_trading_day", return_value=False), \
         patch.object(handlers.summary_service, "build_and_send", bsend):
        await handlers.handle_market_summary(MagicMock(), sched)
    bsend.assert_not_awaited()


@pytest.mark.asyncio
async def test_handler_sends_on_trading_day():
    sched = MagicMock(feature_type=FEATURE_SUMMARY_US)
    bsend = AsyncMock(return_value={"sent": True})
    with patch.object(handlers, "is_trading_day", return_value=True), \
         patch.object(handlers.summary_service, "build_and_send", bsend):
        await handlers.handle_market_summary(MagicMock(), sched)
    bsend.assert_awaited_once()
    assert bsend.await_args.args[1] == "US"


def test_handlers_registry_has_market_summary():
    from app.services.scheduler.schedule_store import FEATURE_SUMMARY_KR
    assert handlers.HANDLERS[FEATURE_SUMMARY_US] is handlers.handle_market_summary
    assert handlers.HANDLERS[FEATURE_SUMMARY_KR] is handlers.handle_market_summary
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_summary_service.py -k handler -v`
Expected: FAIL — `ImportError: cannot import name 'FEATURE_SUMMARY_US'` 또는 `handle_market_summary` 없음

- [ ] **Step 3: 구현**

`app/services/scheduler/schedule_store.py`의 `FEATURE_CHART = "chart_analysis"` 아래에 추가:

```python
FEATURE_SUMMARY_US = "market_summary_us"
FEATURE_SUMMARY_KR = "market_summary_kr"
```

`app/services/scheduler/handlers.py` 상단 import에 추가:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.market.market_hours import is_trading_day
from app.services.market_summary import summary_service
from app.services.notification import telegram_service
from app.services.scheduler.schedule_store import FEATURE_SUMMARY_US, FEATURE_SUMMARY_KR

_KST = ZoneInfo("Asia/Seoul")
```

`handle_chart_analysis` 아래에 추가:

```python
async def handle_market_summary(db: AsyncSession, schedule: Schedule) -> None:
    market = "US" if schedule.feature_type == FEATURE_SUMMARY_US else "KR"
    if not is_trading_day(market, datetime.now(_KST)):
        _log.info("증시 요약 휴장일 스킵 market=%s", market)
        return
    try:
        await summary_service.build_and_send(db, market)
    except telegram_service.TelegramNotConfigured:
        _log.info("텔레그램 미설정 — 증시 요약 발송 생략")
```

`HANDLERS` 딕셔너리를 교체:

```python
HANDLERS = {
    "chart_analysis": handle_chart_analysis,
    FEATURE_SUMMARY_US: handle_market_summary,
    FEATURE_SUMMARY_KR: handle_market_summary,
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_summary_service.py -v`
Run: `.venv/bin/python -c "import app.main"`
Expected: PASS, import 에러 없음

- [ ] **Step 5: 커밋**

```bash
git add app/services/scheduler/schedule_store.py app/services/scheduler/handlers.py tests/test_summary_service.py
git commit -m "feat(summary): 시장별 스케줄 상수 + 핸들러 등록(휴장일 스킵)"
```

---

### Task 7: 라우터 `/api/market-summary`

**Files:**
- Create: `app/routers/market_summary.py`
- Modify: `app/main.py`
- Test: `tests/test_market_summary_api.py`

- [ ] **Step 1: 실패하는 API 테스트 작성**

`tests/test_market_summary_api.py` 생성:

```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_get_schedule_null_when_absent():
    with patch("app.routers.market_summary.schedule_store.get_schedule", AsyncMock(return_value=None)):
        async with await _client() as ac:
            resp = await ac.get("/api/market-summary/US/schedule")
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.asyncio
async def test_get_schedule_invalid_market_404():
    async with await _client() as ac:
        resp = await ac.get("/api/market-summary/JP/schedule")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_put_schedule_rejects_bad_time():
    async with await _client() as ac:
        resp = await ac.put("/api/market-summary/US/schedule",
                            json={"send_time": "99:99", "days_of_week": [0], "enabled": True})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_schedule_upserts_sorted_days():
    with patch("app.routers.market_summary.schedule_store.upsert_schedule", AsyncMock()) as up:
        async with await _client() as ac:
            resp = await ac.put("/api/market-summary/KR/schedule",
                                json={"send_time": "18:00", "days_of_week": [4, 0, 1], "enabled": True})
    assert resp.status_code == 200
    up.assert_awaited_once()
    args = up.await_args.args
    assert args[1] == "market_summary_kr"  # feature_type
    assert args[2] == 0                     # target_id
    assert args[4] == "0,1,4"               # days


@pytest.mark.asyncio
async def test_send_now_invokes_service():
    with patch("app.routers.market_summary.summary_service.build_and_send",
               AsyncMock(return_value={"market": "US", "sent": True, "indices": 3,
                                       "holdings": 1, "watchlist": 0})):
        async with await _client() as ac:
            resp = await ac.post("/api/market-summary/US/send")
    assert resp.status_code == 200
    assert resp.json()["sent"] is True


@pytest.mark.asyncio
async def test_send_now_telegram_not_configured_409():
    from app.services.notification import telegram_service
    with patch("app.routers.market_summary.summary_service.build_and_send",
               AsyncMock(side_effect=telegram_service.TelegramNotConfigured("no token"))):
        async with await _client() as ac:
            resp = await ac.post("/api/market-summary/US/send")
    assert resp.status_code == 409
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_market_summary_api.py -v`
Expected: FAIL — 404(라우터 미등록)/ModuleNotFound

- [ ] **Step 3: 라우터 구현 + 등록**

`app/routers/market_summary.py` 생성:

```python
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.scheduler import schedule_store
from app.services.scheduler.schedule_store import FEATURE_SUMMARY_US, FEATURE_SUMMARY_KR
from app.services.market_summary import summary_service
from app.services.notification import telegram_service

router = APIRouter(prefix="/api/market-summary", tags=["market-summary"])

_FEATURE = {"US": FEATURE_SUMMARY_US, "KR": FEATURE_SUMMARY_KR}


def _feature(market: str) -> str:
    f = _FEATURE.get(market)
    if f is None:
        raise HTTPException(404, "market은 US 또는 KR이어야 합니다.")
    return f


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


@router.get("/{market}/schedule")
async def get_schedule(market: str, db: AsyncSession = Depends(get_db)):
    sched = await schedule_store.get_schedule(db, _feature(market), 0)
    if sched is None:
        return None
    return {
        "send_time": sched.send_time,
        "days_of_week": [int(x) for x in sched.days_of_week.split(",") if x != ""],
        "enabled": sched.enabled,
    }


@router.put("/{market}/schedule")
async def put_schedule(market: str, body: ScheduleIn, db: AsyncSession = Depends(get_db)):
    feature = _feature(market)
    days = ",".join(str(d) for d in sorted(set(body.days_of_week)))
    await schedule_store.upsert_schedule(db, feature, 0, body.send_time, days, body.enabled)
    return {"status": "ok"}


@router.delete("/{market}/schedule")
async def delete_schedule(market: str, db: AsyncSession = Depends(get_db)):
    await schedule_store.delete_schedule(db, _feature(market), 0)
    return {"status": "ok"}


@router.post("/{market}/send")
async def send_now(market: str, db: AsyncSession = Depends(get_db)):
    _feature(market)  # market 검증
    try:
        return await summary_service.build_and_send(db, market)
    except telegram_service.TelegramNotConfigured as e:
        raise HTTPException(409, str(e))
```

`app/main.py` line-12 import에 `market_summary` 추가:

```python
from app.routers import assets, holdings, portfolio, fx, settings as settings_router, cash, charts, watchlist, alerts, market_summary
```

include 루프에 `market_summary.router` 추가:

```python
for r in (assets.router, holdings.router, portfolio.router, fx.router, settings_router.router, cash.router, charts.router, watchlist.router, alerts.router, market_summary.router):
    app.include_router(r)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_market_summary_api.py -v`
Run: `.venv/bin/python -c "import app.main"`
Expected: PASS (6개), import 에러 없음

- [ ] **Step 5: 커밋**

```bash
git add app/routers/market_summary.py app/main.py tests/test_market_summary_api.py
git commit -m "feat(summary): /api/market-summary 라우터(스케줄 CRUD + 즉시발송)"
```

---

### Task 8: 프론트 — api.ts + 설정 섹션

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: api.ts 함수 추가**

`frontend/src/api.ts`의 `api` 객체 안에 추가:

```ts
  getMarketSummarySchedule: (m: string) =>
    j<{ send_time: string; days_of_week: number[]; enabled: boolean } | null>(`/api/market-summary/${m}/schedule`),
  saveMarketSummarySchedule: (m: string, s: { send_time: string; days_of_week: number[]; enabled: boolean }) =>
    j(`/api/market-summary/${m}/schedule`, { method: "PUT", body: JSON.stringify(s) }),
  deleteMarketSummarySchedule: (m: string) =>
    j(`/api/market-summary/${m}/schedule`, { method: "DELETE" }),
  sendMarketSummary: (m: string) =>
    j<{ market: string; sent: boolean; indices: number; holdings: number; watchlist: number }>(`/api/market-summary/${m}/send`, { method: "POST" }),
```

- [ ] **Step 2: Settings.tsx에 증시 요약 섹션 추가**

`frontend/src/pages/Settings.tsx` 상단 import 아래(컴포넌트 함수 `export default function Settings()` **위**)에 재사용 블록 컴포넌트를 추가:

```tsx
const DAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"];

function MarketSummaryBlock({ market, label }: { market: string; label: string }) {
  const [time, setTime] = useState("08:30");
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [enabled, setEnabled] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.getMarketSummarySchedule(market).then((s) => {
      if (s) { setTime(s.send_time); setDays(s.days_of_week); setEnabled(s.enabled); }
    }).catch(() => {});
  }, [market]);

  const toggle = (d: number) =>
    setDays((p) => p.includes(d) ? p.filter((x) => x !== d) : [...p, d].sort());
  const save = async () => {
    setMsg("저장 중…");
    try { await api.saveMarketSummarySchedule(market, { send_time: time, days_of_week: days, enabled }); setMsg("저장됨"); }
    catch (e: any) { setMsg("저장 실패: " + e.message); }
  };
  const remove = async () => {
    setMsg("삭제 중…");
    try { await api.deleteMarketSummarySchedule(market); setEnabled(false); setMsg("삭제됨"); }
    catch (e: any) { setMsg("삭제 실패: " + e.message); }
  };
  const sendNow = async () => {
    setMsg("발송 중…");
    try { const r = await api.sendMarketSummary(market); setMsg(r.sent ? `발송 완료(지수 ${r.indices}·보유 ${r.holdings}·관심 ${r.watchlist})` : "발송 실패"); }
    catch (e: any) { setMsg("발송 실패: " + e.message); }
  };

  return (
    <div className="border rounded p-3 space-y-2">
      <div className="font-medium">{label}</div>
      <div className="flex items-center gap-2 flex-wrap">
        <label className="text-sm">시각</label>
        <input type="time" className="border rounded px-2 py-1" value={time} onChange={(e) => setTime(e.target.value)} />
        <span className="text-xs text-gray-500">(KST)</span>
      </div>
      <div className="flex items-center gap-1 flex-wrap">
        {DAY_LABELS.map((lbl, d) => (
          <button key={d} type="button" onClick={() => toggle(d)}
            className={`px-2 py-1 rounded text-sm border ${days.includes(d) ? "bg-blue-600 text-white" : "bg-gray-100"}`}>{lbl}</button>
        ))}
      </div>
      <label className="flex gap-2 items-center text-sm">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        활성화
      </label>
      <div className="flex gap-2 items-center">
        <button onClick={save} className="px-3 py-1 rounded bg-blue-600 text-white">저장</button>
        <button onClick={remove} className="px-3 py-1 rounded bg-gray-500 text-white">삭제</button>
        <button onClick={sendNow} className="px-3 py-1 rounded bg-emerald-600 text-white">지금 발송</button>
        {msg && <span className="text-sm text-gray-600">{msg}</span>}
      </div>
    </div>
  );
}
```

그리고 Settings의 반환 JSX에서 마지막 `</section>`(AI 분석 섹션) 다음, 최상위 `</div>` 앞에 섹션 추가:

```tsx
      <section className="space-y-2">
        <h2 className="font-semibold text-gray-700">증시 마감 요약</h2>
        <MarketSummaryBlock market="US" label="미국 증시 (US)" />
        <MarketSummaryBlock market="KR" label="한국 증시 (KR)" />
      </section>
```

- [ ] **Step 3: 빌드 확인**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: 타입 에러 없음, 빌드 성공

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/api.ts frontend/src/pages/Settings.tsx
git commit -m "feat(summary): 설정 페이지 증시 요약 스케줄 섹션 + api"
```

---

### Task 9: 전체 검증

**Files:** 없음(검증만)

- [ ] **Step 1: 백엔드 전체 테스트(실 DB)**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q`
Expected: 신규 테스트 포함 전부 PASS, 기존 회귀 없음

- [ ] **Step 2: import 스모크**

Run: `.venv/bin/python -c "import app.main"`
Expected: 에러 없음

- [ ] **Step 3: 프론트 빌드**

Run: `cd frontend && npm run build`
Expected: 성공

- [ ] **Step 4: 수동 스모크(앱 실행)**

- 설정 페이지에 "증시 마감 요약" US/KR 블록 노출
- US "지금 발송" → 텔레그램 수신(지수 + 보유/관심 US 종목), 응답 카운트 표시
- 시각·요일 저장 후 재로드 시 유지, 삭제 동작

---

## Self-Review (작성자 점검 결과)

- **스펙 커버리지**: is_trading_day(T1)·asset_stats(T2)·index_lines(T3)·message(T4)·build_and_send(T5)·스케줄상수+핸들러+휴장스킵(T6)·라우터 CRUD+send(T7)·프론트(T8)·검증(T9). spec의 결정·아키텍처·API·UI·테스트 모두 대응. 비목표(JP/코인·사용자지수·통합요약·이력로그) 미구현 유지.
- **Placeholder 스캔**: 모든 스텝 실제 코드/명령 포함. 없음.
- **타입 일관성**: `asset_stats`(dict|None, 키 current/daily_pct/weekly_pct/monthly_pct/wk52_high/wk52_drop_pct) → message.build_message·summary_service에서 동일 키 사용. `index_lines`(list[{name,price,change_pct}]) 일관. `build_message(market, indices, holdings_stats, watchlist_stats)`에서 stats 행은 `(name, ticker, dict)` — summary_service가 그 형태로 구성. 핸들러 레지스트리 키 = schedule_store 상수와 일치. 라우터 feature 매핑(US/KR)·target_id=0 일관.
- **순환 import 점검**: handlers→summary_service→portfolio_service/telegram_service/market_summary.*; handlers→schedule_store(상수)·market_hours. dispatcher→handlers. scheduler→dispatcher. 순환 없음(import 스모크로 확인).
