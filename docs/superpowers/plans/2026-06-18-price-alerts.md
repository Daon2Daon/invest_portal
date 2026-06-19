# 가격 알림 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 자산별 가격 도달 조건(절대가/평균매입가/52주 고저점 기준)을 5분 주기로 장중에 평가해 텔레그램으로 1회 알린다.

**Architecture:** 기존 scheduler/store/dispatcher 관례를 복제한다. `PriceAlert` 모델 + 순수 평가함수(evaluator) + 기준가 조회(basis) + 메시지(message) + CRUD(store) + 5분 디스패처 + 라우터로 분해하고, 시장 개장 판정(market_hours)은 `pandas_market_calendars`로 한다. UI는 스펙 A의 자산 상세 허브(`AssetDetail.tsx`)에 "가격 알림" 섹션으로 편입한다.

**Tech Stack:** FastAPI + async SQLAlchemy 2.0(asyncpg/PostgreSQL), APScheduler, pandas_market_calendars, pytest/pytest-asyncio + httpx ASGITransport, React 19 + react-router v7 + Tailwind/Vite/TS.

설계 spec: `docs/superpowers/specs/2026-06-18-price-alerts-design.md`

---

## 파일 구조

신규
- `app/models/price_alert.py` — `PriceAlert` ORM
- `app/services/alert/__init__.py` (빈 패키지)
- `app/services/alert/evaluator.py` — `compute_target`, `is_fired` (순수)
- `app/services/alert/message.py` — `build_message` (순수)
- `app/services/alert/basis.py` — `resolve_basis_price` + WEEK52 TTL 캐시
- `app/services/alert/alert_store.py` — CRUD + `list_active_with_assets` + `has_holdings` + `list_alerts_view`
- `app/services/alert/alert_dispatcher.py` — `evaluate_tick`
- `app/services/market/market_hours.py` — `is_market_open`
- `app/schemas/alert.py` — `AlertCreate/AlertUpdate/AlertOut`
- `app/routers/alerts.py` — `/api/alerts` CRUD + rearm
- `tests/test_alert_evaluator.py`, `test_alert_message.py`, `test_market_hours.py`, `test_alert_basis.py`, `test_alert_store.py`, `test_alert_dispatcher.py`, `test_alerts_api.py`

수정
- `requirements.txt` — `pandas_market_calendars` 추가
- `app/models/__init__.py` — `PriceAlert` 등록
- `app/services/scheduler/scheduler.py` — 5분 `alert_tick` 잡 추가
- `app/main.py` — alerts 라우터 등록
- `frontend/src/api.ts` — alert 함수·타입
- `frontend/src/pages/AssetDetail.tsx` — 가격 알림 섹션

> 모든 pytest/python 명령은 프로젝트 venv로 실행: 예 `.venv/bin/pytest ...`. DB 통합 테스트는 다음 환경에서만 실제 실행됨(미설정 시 skip):
> `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db'`

---

### Task 1: 의존성 + PriceAlert 모델

**Files:**
- Modify: `requirements.txt`
- Create: `app/models/price_alert.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_alert_store.py` (모델 생성 smoke만; CRUD는 Task 6)

- [ ] **Step 1: requirements에 의존성 추가**

`requirements.txt`의 `pykrx>=1.0.45` 줄 아래(또는 적당한 위치)에 추가:

```
pandas_market_calendars>=4.0.0
```

설치: `.venv/bin/pip install pandas_market_calendars`

- [ ] **Step 2: 실패하는 모델 생성 테스트 작성**

`tests/test_alert_store.py` 생성(우선 모델 import + 생성 smoke만):

```python
import pytest
from app.models import Asset, PriceAlert


def _asset(**kw):
    base = dict(ticker="T", name="N", asset_type="stock", market="US",
                currency="USD", data_source="yfinance", fetch_symbol="T")
    base.update(kw)
    return Asset(**base)


@pytest.mark.asyncio
async def test_create_price_alert_row(db_session):
    a = _asset(ticker="AAA", fetch_symbol="AAA")
    db_session.add(a)
    await db_session.commit()
    alert = PriceAlert(asset_id=a.asset_id, basis="ABSOLUTE", direction="ABOVE", value=250)
    db_session.add(alert)
    await db_session.commit()
    assert alert.alert_id is not None
    assert alert.enabled is True
    assert alert.is_triggered is False
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_alert_store.py -v`
Expected: FAIL — `ImportError: cannot import name 'PriceAlert'`

- [ ] **Step 4: 모델 구현**

`app/models/price_alert.py` 생성:

```python
from datetime import datetime
from sqlalchemy import String, Boolean, Numeric, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class PriceAlert(Base):
    __tablename__ = "price_alerts"

    alert_id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False, index=True)
    basis: Mapped[str] = mapped_column(String, nullable=False)       # ABSOLUTE/PURCHASE_AVG/WEEK52_HIGH/WEEK52_LOW
    direction: Mapped[str] = mapped_column(String, nullable=False)   # ABOVE/BELOW
    value: Mapped[float] = mapped_column(Numeric, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_triggered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

`app/models/__init__.py`에 등록:

```python
from app.models.price_alert import PriceAlert
```

그리고 `__all__` 리스트에 `"PriceAlert"` 추가.

- [ ] **Step 5: 테스트 통과 + import 확인**

Run: `.venv/bin/pytest tests/test_alert_store.py -v` → PASS 또는 SKIP
Run: `.venv/bin/python -c "import app.main"` → 에러 없음

- [ ] **Step 6: 커밋**

```bash
git add requirements.txt app/models/price_alert.py app/models/__init__.py tests/test_alert_store.py
git commit -m "feat(alert): PriceAlert 모델 + pandas_market_calendars 의존성"
```

---

### Task 2: 순수 평가함수 evaluator

**Files:**
- Create: `app/services/alert/__init__.py` (빈 파일)
- Create: `app/services/alert/evaluator.py`
- Test: `tests/test_alert_evaluator.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_alert_evaluator.py` 생성:

```python
from app.services.alert.evaluator import compute_target, is_fired


def test_absolute_ignores_basis_price():
    assert compute_target("ABSOLUTE", "ABOVE", 250.0, None) == 250.0
    assert compute_target("ABSOLUTE", "BELOW", 70000.0, None) == 70000.0


def test_purchase_avg_below_15pct():
    assert compute_target("PURCHASE_AVG", "BELOW", 15.0, 100.0) == 85.0


def test_purchase_avg_above_20pct():
    assert compute_target("PURCHASE_AVG", "ABOVE", 20.0, 100.0) == 120.0


def test_week52_high_below_10pct():
    assert compute_target("WEEK52_HIGH", "BELOW", 10.0, 200.0) == 180.0


def test_week52_low_above_20pct():
    assert compute_target("WEEK52_LOW", "ABOVE", 20.0, 100.0) == 120.0


def test_is_fired_above_boundary_inclusive():
    assert is_fired("ABOVE", 100.0, 100.0) is True
    assert is_fired("ABOVE", 99.9, 100.0) is False


def test_is_fired_below_boundary_inclusive():
    assert is_fired("BELOW", 100.0, 100.0) is True
    assert is_fired("BELOW", 100.1, 100.0) is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_alert_evaluator.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.alert.evaluator`

- [ ] **Step 3: 구현**

`app/services/alert/__init__.py` 생성(빈 파일).

`app/services/alert/evaluator.py` 생성:

```python
"""가격 알림 순수 평가함수(네트워크/DB 없음)."""


def compute_target(basis: str, direction: str, value: float,
                   basis_price: float | None) -> float:
    """목표가 산출. ABSOLUTE는 value 그대로, 그 외는 기준가×(1±value%)."""
    if basis == "ABSOLUTE":
        return value
    sign = 1.0 if direction == "ABOVE" else -1.0
    return basis_price * (1.0 + sign * value / 100.0)


def is_fired(direction: str, current_price: float, target_price: float) -> bool:
    """ABOVE → 현재가 ≥ 목표가, BELOW → 현재가 ≤ 목표가 (경계 포함)."""
    if direction == "ABOVE":
        return current_price >= target_price
    return current_price <= target_price
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_alert_evaluator.py -v`
Expected: PASS (7개)

- [ ] **Step 5: 커밋**

```bash
git add app/services/alert/__init__.py app/services/alert/evaluator.py tests/test_alert_evaluator.py
git commit -m "feat(alert): 순수 평가함수 compute_target/is_fired"
```

---

### Task 3: 메시지 빌더 message

**Files:**
- Create: `app/services/alert/message.py`
- Test: `tests/test_alert_message.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_alert_message.py` 생성:

```python
from types import SimpleNamespace
from app.services.alert.message import build_message


def _asset(currency="USD"):
    return SimpleNamespace(name="Tesla", ticker="TSLA", market="US", currency=currency)


def test_message_absolute_usd():
    alert = SimpleNamespace(basis="ABSOLUTE", direction="ABOVE", value=250.0)
    msg = build_message(_asset("USD"), alert, current_price=251.0, target_price=250.0)
    assert "TSLA" in msg
    assert "$251.00" in msg
    assert "$250.00" in msg
    assert "≥" in msg


def test_message_purchase_avg_krw():
    asset = SimpleNamespace(name="삼성전자", ticker="005930", market="KR", currency="KRW")
    alert = SimpleNamespace(basis="PURCHASE_AVG", direction="BELOW", value=15.0)
    msg = build_message(asset, alert, current_price=59500.0, target_price=59500.0)
    assert "평균매입가 대비" in msg
    assert "-15%" in msg
    assert "59,500원" in msg
    assert "≤" in msg
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_alert_message.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.alert.message`

- [ ] **Step 3: 구현**

`app/services/alert/message.py` 생성:

```python
"""가격 알림 텔레그램 메시지(HTML) 빌더. asset/alert는 속성 접근만 한다(ORM 또는 단순객체)."""

_BASIS_LABEL = {
    "ABSOLUTE": "목표가",
    "PURCHASE_AVG": "평균매입가 대비",
    "WEEK52_HIGH": "52주 고점 대비",
    "WEEK52_LOW": "52주 저점 대비",
}


def _fmt(price: float, currency: str) -> str:
    if currency == "KRW":
        return f"{price:,.0f}원"
    sym = {"USD": "$", "JPY": "¥"}.get(currency, "")
    return f"{sym}{price:,.2f}"


def build_message(asset, alert, current_price: float, target_price: float) -> str:
    arrow = "≥" if alert.direction == "ABOVE" else "≤"
    if alert.basis == "ABSOLUTE":
        edge = "이상" if alert.direction == "ABOVE" else "이하"
        cond = f"{_BASIS_LABEL['ABSOLUTE']} {_fmt(float(alert.value), asset.currency)} {edge}"
    else:
        sign = "+" if alert.direction == "ABOVE" else "-"
        cond = f"{_BASIS_LABEL[alert.basis]} {sign}{float(alert.value):g}% 도달"
    return (
        f"🔔 <b>{asset.name}</b> ({asset.ticker}·{asset.market})\n"
        f"조건: {cond}\n"
        f"현재가 {_fmt(current_price, asset.currency)} {arrow} 목표 {_fmt(target_price, asset.currency)}"
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_alert_message.py -v`
Expected: PASS (2개)

- [ ] **Step 5: 커밋**

```bash
git add app/services/alert/message.py tests/test_alert_message.py
git commit -m "feat(alert): 텔레그램 메시지 빌더"
```

---

### Task 4: 시장 개장 판정 market_hours

**Files:**
- Create: `app/services/market/market_hours.py`
- Test: `tests/test_market_hours.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_market_hours.py` 생성(고정 UTC datetime, 캘린더는 결정적):

```python
import datetime as dt
from datetime import timezone
from app.services.market.market_hours import is_market_open


def _utc(y, m, d, hh, mm):
    return dt.datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def test_crypto_always_open():
    assert is_market_open("CRYPTO", _utc(2026, 6, 20, 3, 0)) is True  # 주말이어도


def test_unknown_market_fail_open():
    assert is_market_open("XX", _utc(2026, 6, 17, 3, 0)) is True


def test_nyse_open_during_session():
    # 2026-06-17(수) 15:00 UTC = 11:00 ET → 개장
    assert is_market_open("US", _utc(2026, 6, 17, 15, 0)) is True


def test_nyse_closed_premarket():
    # 2026-06-17 08:00 UTC = 04:00 ET → 폐장
    assert is_market_open("US", _utc(2026, 6, 17, 8, 0)) is False


def test_nyse_closed_weekend():
    # 2026-06-20 토요일
    assert is_market_open("US", _utc(2026, 6, 20, 15, 0)) is False


def test_xkrx_open_during_session():
    # 2026-06-17 01:00 UTC = 10:00 KST → 개장
    assert is_market_open("KR", _utc(2026, 6, 17, 1, 0)) is True


def test_xkrx_closed_after_hours():
    # 2026-06-17 12:00 UTC = 21:00 KST → 폐장
    assert is_market_open("KR", _utc(2026, 6, 17, 12, 0)) is False


def test_jpx_open_during_session():
    # 2026-06-17 01:00 UTC = 10:00 JST → 개장
    assert is_market_open("JP", _utc(2026, 6, 17, 1, 0)) is True
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_market_hours.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.market.market_hours`

- [ ] **Step 3: 구현**

`app/services/market/market_hours.py` 생성:

```python
"""시장 개장(거래일+장중) 판정. now는 tz-aware datetime을 인자로 받아 순수·결정적이다.
점심 휴장(예: JPX)은 단순화해 무시한다(개인용 알림 영향 경미)."""
from datetime import datetime, timezone, timedelta

_CAL_NAMES = {"US": "NYSE", "KR": "XKRX", "JP": "JPX"}
_cal_cache: dict = {}


def _calendar(name: str):
    if name not in _cal_cache:
        import pandas_market_calendars as mcal
        _cal_cache[name] = mcal.get_calendar(name)
    return _cal_cache[name]


def is_market_open(market: str, now: datetime) -> bool:
    if market == "CRYPTO":
        return True
    name = _CAL_NAMES.get(market)
    if name is None:
        return True  # 미지 시장 → fail-open(알림 누락 방지)
    try:
        cal = _calendar(name)
        now_utc = now.astimezone(timezone.utc)
        start = (now_utc - timedelta(days=1)).date().isoformat()
        end = (now_utc + timedelta(days=1)).date().isoformat()
        sched = cal.schedule(start_date=start, end_date=end)
        for _, row in sched.iterrows():
            if row["market_open"] <= now_utc <= row["market_close"]:
                return True
        return False
    except Exception:
        return True  # 라이브러리 오류 → fail-open
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_market_hours.py -v`
Expected: PASS (8개). (pandas_market_calendars의 break 관련 UserWarning은 무시해도 됨)

- [ ] **Step 5: 커밋**

```bash
git add app/services/market/market_hours.py tests/test_market_hours.py
git commit -m "feat(alert): 시장 개장 판정 market_hours"
```

---

### Task 5: 기준가 조회 basis (+ WEEK52 캐시)

**Files:**
- Create: `app/services/alert/basis.py`
- Test: `tests/test_alert_basis.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_alert_basis.py` 생성:

```python
import pytest
import pandas as pd
from unittest.mock import patch, AsyncMock

from app.models import Asset, Holding
from app.services.alert.basis import resolve_basis_price, clear_week52_cache


def _asset(**kw):
    base = dict(ticker="T", name="N", asset_type="stock", market="US",
                currency="USD", data_source="yfinance", fetch_symbol="T")
    base.update(kw)
    return Asset(**base)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_week52_cache()
    yield
    clear_week52_cache()


@pytest.mark.asyncio
async def test_absolute_returns_none(db_session):
    a = _asset(ticker="AAA", fetch_symbol="AAA")
    db_session.add(a); await db_session.commit()
    assert await resolve_basis_price(db_session, a, "ABSOLUTE") is None


@pytest.mark.asyncio
async def test_purchase_avg_weighted(db_session):
    a = _asset(ticker="BBB", fetch_symbol="BBB")
    db_session.add(a); await db_session.commit()
    db_session.add_all([
        Holding(asset_id=a.asset_id, quantity=10, purchase_price=100, fee=0),
        Holding(asset_id=a.asset_id, quantity=30, purchase_price=200, fee=0),
    ])
    await db_session.commit()
    # (10*100 + 30*200) / 40 = 175
    assert await resolve_basis_price(db_session, a, "PURCHASE_AVG") == 175.0


@pytest.mark.asyncio
async def test_purchase_avg_none_when_no_lots(db_session):
    a = _asset(ticker="CCC", fetch_symbol="CCC")
    db_session.add(a); await db_session.commit()
    assert await resolve_basis_price(db_session, a, "PURCHASE_AVG") is None


@pytest.mark.asyncio
async def test_week52_high_low_and_cache(db_session):
    a = _asset(ticker="DDD", fetch_symbol="DDD")
    db_session.add(a); await db_session.commit()
    df = pd.DataFrame({"High": [10.0, 30.0, 20.0], "Low": [5.0, 8.0, 6.0]})
    mock = AsyncMock(return_value=df)
    with patch("app.services.alert.basis.get_history", mock):
        assert await resolve_basis_price(db_session, a, "WEEK52_HIGH") == 30.0
        assert await resolve_basis_price(db_session, a, "WEEK52_LOW") == 5.0
    # 두 번째 호출은 캐시 사용 → get_history 1회만 호출
    assert mock.await_count == 1


@pytest.mark.asyncio
async def test_week52_none_when_no_history(db_session):
    a = _asset(ticker="EEE", fetch_symbol="EEE")
    db_session.add(a); await db_session.commit()
    with patch("app.services.alert.basis.get_history", AsyncMock(return_value=None)):
        assert await resolve_basis_price(db_session, a, "WEEK52_HIGH") is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_alert_basis.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.alert.basis`

- [ ] **Step 3: 구현**

`app/services/alert/basis.py` 생성:

```python
"""알림 기준가 조회. WEEK52는 yfinance 호출 절감을 위해 자산별 TTL 캐시(기본 1시간)."""
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Holding
from app.services.market.history_service import get_history

_WEEK52_TTL = 3600.0
_WEEK52_CACHE: dict[int, tuple[float, float, float]] = {}   # asset_id -> (high, low, fetched_monotonic)


def clear_week52_cache() -> None:
    _WEEK52_CACHE.clear()


async def _purchase_avg(db: AsyncSession, asset_id: int) -> float | None:
    lots = (await db.execute(
        select(Holding).where(Holding.asset_id == asset_id)
    )).scalars().all()
    total_qty = sum(float(l.quantity) for l in lots)
    if not lots or total_qty == 0:
        return None
    return sum(float(l.quantity) * float(l.purchase_price) for l in lots) / total_qty


async def _week52(db: AsyncSession, asset) -> tuple[float, float] | None:
    cached = _WEEK52_CACHE.get(asset.asset_id)
    if cached and (time.monotonic() - cached[2]) < _WEEK52_TTL:
        return cached[0], cached[1]
    df = await get_history(asset, 365)
    if df is None or df.empty:
        return None
    high = float(df["High"].max())
    low = float(df["Low"].min())
    _WEEK52_CACHE[asset.asset_id] = (high, low, time.monotonic())
    return high, low


async def resolve_basis_price(db: AsyncSession, asset, basis: str) -> float | None:
    """ABSOLUTE→None(목표가가 value), PURCHASE_AVG→가중평균, WEEK52_*→고/저점. 불가 시 None."""
    if basis == "ABSOLUTE":
        return None
    if basis == "PURCHASE_AVG":
        return await _purchase_avg(db, asset.asset_id)
    if basis in ("WEEK52_HIGH", "WEEK52_LOW"):
        hl = await _week52(db, asset)
        if hl is None:
            return None
        return hl[0] if basis == "WEEK52_HIGH" else hl[1]
    return None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_alert_basis.py -v`
Expected: PASS (5개) 또는 SKIP

- [ ] **Step 5: 커밋**

```bash
git add app/services/alert/basis.py tests/test_alert_basis.py
git commit -m "feat(alert): 기준가 조회 basis + WEEK52 TTL 캐시"
```

---

### Task 6: CRUD store + 스키마

**Files:**
- Create: `app/services/alert/alert_store.py`
- Create: `app/schemas/alert.py`
- Test: `tests/test_alert_store.py` (Task 1에서 생성, CRUD 테스트 추가)

- [ ] **Step 1: 실패하는 CRUD 테스트 추가**

`tests/test_alert_store.py` 끝에 추가:

```python
from app.services.alert import alert_store


@pytest.mark.asyncio
async def test_store_crud_and_rearm(db_session):
    a = _asset(ticker="STORE", fetch_symbol="STORE")
    db_session.add(a); await db_session.commit()
    alert = await alert_store.create_alert(
        db_session, a.asset_id, "ABSOLUTE", "ABOVE", 250.0, note="hi")
    assert alert.alert_id is not None

    # update
    alert = await alert_store.update_alert(db_session, alert, value=260.0, enabled=False)
    assert float(alert.value) == 260.0
    assert alert.enabled is False

    # simulate fired then rearm
    alert.is_triggered = True
    await db_session.commit()
    alert = await alert_store.rearm_alert(db_session, alert)
    assert alert.enabled is True
    assert alert.is_triggered is False
    assert alert.triggered_at is None

    # list_by_asset
    rows = await alert_store.list_by_asset(db_session, a.asset_id)
    assert len(rows) == 1

    # has_holdings False (no lots)
    assert await alert_store.has_holdings(db_session, a.asset_id) is False

    # delete
    await alert_store.delete_alert(db_session, alert)
    assert await alert_store.list_by_asset(db_session, a.asset_id) == []


@pytest.mark.asyncio
async def test_list_active_with_assets_filters(db_session):
    active = _asset(ticker="ACT", fetch_symbol="ACT")
    inactive = _asset(ticker="INA", fetch_symbol="INA", is_active=False)
    db_session.add_all([active, inactive]); await db_session.commit()
    # active asset: one enabled alert + one triggered (excluded)
    await alert_store.create_alert(db_session, active.asset_id, "ABSOLUTE", "ABOVE", 1.0)
    triggered = await alert_store.create_alert(db_session, active.asset_id, "ABSOLUTE", "ABOVE", 2.0)
    triggered.is_triggered = True
    # inactive asset alert (excluded by asset.is_active)
    await alert_store.create_alert(db_session, inactive.asset_id, "ABSOLUTE", "ABOVE", 3.0)
    await db_session.commit()
    pairs = await alert_store.list_active_with_assets(db_session)
    values = sorted(float(al.value) for al, _ in pairs)
    assert values == [1.0]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_alert_store.py -v`
Expected: FAIL — `AttributeError: module 'app.services.alert.alert_store' has no attribute ...` (또는 ModuleNotFound)

- [ ] **Step 3: store 구현**

`app/services/alert/alert_store.py` 생성:

```python
"""price_alerts CRUD + 조회. 라우터·디스패처가 공유."""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, Holding, PriceAlert

_UNSET = object()


async def create_alert(db: AsyncSession, asset_id: int, basis: str, direction: str,
                       value: float, note: str | None = None) -> PriceAlert:
    alert = PriceAlert(asset_id=asset_id, basis=basis, direction=direction,
                       value=value, note=note)
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


async def get_alert(db: AsyncSession, alert_id: int) -> PriceAlert | None:
    return await db.get(PriceAlert, alert_id)


async def list_by_asset(db: AsyncSession, asset_id: int) -> list[PriceAlert]:
    return list((await db.execute(
        select(PriceAlert).where(PriceAlert.asset_id == asset_id).order_by(PriceAlert.alert_id)
    )).scalars().all())


async def list_active_with_assets(db: AsyncSession) -> list[tuple[PriceAlert, Asset]]:
    """enabled & not triggered 알림 + 활성 자산 조인. (alert, asset) 튜플 리스트."""
    rows = (await db.execute(
        select(PriceAlert, Asset).join(Asset, Asset.asset_id == PriceAlert.asset_id).where(
            PriceAlert.enabled.is_(True),
            PriceAlert.is_triggered.is_(False),
            Asset.is_active.is_(True),
        )
    )).all()
    return [(r[0], r[1]) for r in rows]


async def has_holdings(db: AsyncSession, asset_id: int) -> bool:
    n = (await db.execute(
        select(func.count()).select_from(Holding).where(Holding.asset_id == asset_id)
    )).scalar_one()
    return n > 0


async def update_alert(db: AsyncSession, alert: PriceAlert, *, value=None, direction=None,
                       note=_UNSET, enabled=None) -> PriceAlert:
    if value is not None:
        alert.value = value
    if direction is not None:
        alert.direction = direction
    if note is not _UNSET:
        alert.note = note
    if enabled is not None:
        alert.enabled = enabled
    await db.commit()
    await db.refresh(alert)
    return alert


async def rearm_alert(db: AsyncSession, alert: PriceAlert) -> PriceAlert:
    alert.enabled = True
    alert.is_triggered = False
    alert.triggered_at = None
    await db.commit()
    await db.refresh(alert)
    return alert


async def delete_alert(db: AsyncSession, alert: PriceAlert) -> None:
    await db.delete(alert)
    await db.commit()
```

`app/schemas/alert.py` 생성:

```python
from typing import Literal
from pydantic import BaseModel, field_validator

Basis = Literal["ABSOLUTE", "PURCHASE_AVG", "WEEK52_HIGH", "WEEK52_LOW"]
Direction = Literal["ABOVE", "BELOW"]


class AlertCreate(BaseModel):
    asset_id: int
    basis: Basis
    direction: Direction
    value: float
    note: str | None = None

    @field_validator("value")
    @classmethod
    def _positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("value는 0보다 커야 합니다.")
        return v


class AlertUpdate(BaseModel):
    value: float | None = None
    direction: Direction | None = None
    note: str | None = None
    enabled: bool | None = None

    @field_validator("value")
    @classmethod
    def _positive(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("value는 0보다 커야 합니다.")
        return v


class AlertOut(BaseModel):
    alert_id: int
    asset_id: int
    basis: str
    direction: str
    value: float
    enabled: bool
    is_triggered: bool
    note: str | None = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_alert_store.py -v`
Expected: PASS (3개: row smoke + crud + filter) 또는 SKIP

- [ ] **Step 5: 커밋**

```bash
git add app/services/alert/alert_store.py app/schemas/alert.py tests/test_alert_store.py
git commit -m "feat(alert): CRUD store + pydantic 스키마"
```

---

### Task 7: 디스패처 evaluate_tick

**Files:**
- Create: `app/services/alert/alert_dispatcher.py`
- Test: `tests/test_alert_dispatcher.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_alert_dispatcher.py` 생성(SessionLocal·의존성 전부 patch, DB 불필요):

```python
import pytest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock, MagicMock

from app.services.market.types import Quote
import app.services.alert.alert_dispatcher as disp


class _FakeSession:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def commit(self): pass
    async def rollback(self): pass


def _asset(asset_id=1, market="US"):
    return SimpleNamespace(asset_id=asset_id, market=market, name="N", ticker="T", currency="USD")


def _alert(alert_id=1, basis="ABSOLUTE", direction="ABOVE", value=100.0):
    return SimpleNamespace(alert_id=alert_id, basis=basis, direction=direction, value=value,
                           enabled=True, is_triggered=False, triggered_at=None, last_notified_at=None)


def _patches(pairs, quote, market_open=True, send_ok=True, basis_price=None):
    return [
        patch.object(disp, "SessionLocal", return_value=_FakeSession()),
        patch.object(disp.alert_store, "list_active_with_assets", AsyncMock(return_value=pairs)),
        patch.object(disp, "is_market_open", return_value=market_open),
        patch.object(disp, "get_quote", AsyncMock(return_value=quote)),
        patch.object(disp, "resolve_basis_price", AsyncMock(return_value=basis_price)),
        patch.object(disp.telegram_service, "send_message", AsyncMock(return_value=send_ok)),
        patch.object(disp.asyncio, "sleep", AsyncMock()),
    ]


async def _run(ctxs):
    started = [c.__enter__() for c in ctxs]
    try:
        await disp.evaluate_tick()
    finally:
        for c in ctxs:
            c.__exit__(None, None, None)
    return started


@pytest.mark.asyncio
async def test_fires_and_updates_state():
    asset, alert = _asset(), _alert(value=100.0)
    q = Quote(price=150.0, currency="USD", status="ok")
    ctxs = _patches([(alert, asset)], q)
    await _run(ctxs)
    assert alert.is_triggered is True
    assert alert.enabled is False
    assert alert.triggered_at is not None


@pytest.mark.asyncio
async def test_skips_when_market_closed():
    asset, alert = _asset(), _alert()
    q = Quote(price=150.0, currency="USD", status="ok")
    send = AsyncMock(return_value=True)
    with patch.object(disp, "SessionLocal", return_value=_FakeSession()), \
         patch.object(disp.alert_store, "list_active_with_assets", AsyncMock(return_value=[(alert, asset)])), \
         patch.object(disp, "is_market_open", return_value=False), \
         patch.object(disp, "get_quote", AsyncMock(return_value=q)) as gq, \
         patch.object(disp.telegram_service, "send_message", send):
        await disp.evaluate_tick()
    gq.assert_not_awaited()
    send.assert_not_awaited()
    assert alert.is_triggered is False


@pytest.mark.asyncio
async def test_skips_when_quote_error():
    asset, alert = _asset(), _alert()
    q = Quote(price=0.0, currency="USD", status="error")
    send = AsyncMock(return_value=True)
    with patch.object(disp, "SessionLocal", return_value=_FakeSession()), \
         patch.object(disp.alert_store, "list_active_with_assets", AsyncMock(return_value=[(alert, asset)])), \
         patch.object(disp, "is_market_open", return_value=True), \
         patch.object(disp, "get_quote", AsyncMock(return_value=q)), \
         patch.object(disp.telegram_service, "send_message", send):
        await disp.evaluate_tick()
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_quote_fetched_once_per_asset():
    asset = _asset()
    a1, a2 = _alert(alert_id=1, value=100.0), _alert(alert_id=2, value=120.0)
    q = Quote(price=150.0, currency="USD", status="ok")
    with patch.object(disp, "SessionLocal", return_value=_FakeSession()), \
         patch.object(disp.alert_store, "list_active_with_assets", AsyncMock(return_value=[(a1, asset), (a2, asset)])), \
         patch.object(disp, "is_market_open", return_value=True), \
         patch.object(disp, "get_quote", AsyncMock(return_value=q)) as gq, \
         patch.object(disp, "resolve_basis_price", AsyncMock(return_value=None)), \
         patch.object(disp.telegram_service, "send_message", AsyncMock(return_value=True)), \
         patch.object(disp.asyncio, "sleep", AsyncMock()):
        await disp.evaluate_tick()
    assert gq.await_count == 1
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_alert_dispatcher.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.alert.alert_dispatcher`

- [ ] **Step 3: 구현**

`app/services/alert/alert_dispatcher.py` 생성:

```python
"""5분 tick: 활성 알림을 자산별로 묶어 장중에만 평가하고, 발동 시 텔레그램 1회 발송."""
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.db import SessionLocal
from app.services.alert import alert_store
from app.services.alert.basis import resolve_basis_price
from app.services.alert.evaluator import compute_target, is_fired
from app.services.alert.message import build_message
from app.services.market.market_hours import is_market_open
from app.services.market.quote_service import get_quote
from app.services.notification import telegram_service

_KST = ZoneInfo("Asia/Seoul")
_log = logging.getLogger(__name__)


async def evaluate_tick() -> None:
    now = datetime.now(_KST)
    async with SessionLocal() as db:
        pairs = await alert_store.list_active_with_assets(db)
        # 자산별 그룹: asset_id -> (asset, [alert, ...])
        by_asset: dict[int, tuple] = {}
        for alert, asset in pairs:
            by_asset.setdefault(asset.asset_id, (asset, []))[1].append(alert)

        for asset, alerts in by_asset.values():
            if not is_market_open(asset.market, now):
                continue
            try:
                quote = await get_quote(asset)
            except Exception as e:   # noqa: BLE001
                _log.warning("시세 조회 실패 asset_id=%s: %s", asset.asset_id, e)
                continue
            if quote.status != "ok" or not quote.price:
                continue
            for alert in alerts:
                try:
                    basis_price = await resolve_basis_price(db, asset, alert.basis)
                    if basis_price is None and alert.basis != "ABSOLUTE":
                        continue
                    target = compute_target(alert.basis, alert.direction, float(alert.value), basis_price)
                    if not is_fired(alert.direction, quote.price, target):
                        continue
                    msg = build_message(asset, alert, quote.price, target)
                    try:
                        ok = await telegram_service.send_message(db, msg)
                    except telegram_service.TelegramNotConfigured:
                        _log.info("텔레그램 미설정 — 알림 발송 생략")
                        return
                    if ok:
                        alert.enabled = False
                        alert.is_triggered = True
                        alert.triggered_at = now
                        alert.last_notified_at = now
                        await db.commit()
                    await asyncio.sleep(2)   # 텔레그램 rate-limit 여유
                except Exception as e:   # noqa: BLE001 — 한 건 실패가 나머지를 막지 않게
                    await db.rollback()
                    _log.warning("알림 평가 실패 alert_id=%s: %s", alert.alert_id, e)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_alert_dispatcher.py -v`
Expected: PASS (4개)

- [ ] **Step 5: 커밋**

```bash
git add app/services/alert/alert_dispatcher.py tests/test_alert_dispatcher.py
git commit -m "feat(alert): 5분 디스패처 evaluate_tick"
```

---

### Task 8: 라우터 + 라이브 뷰 + 등록

**Files:**
- Modify: `app/services/alert/alert_store.py` (`list_alerts_view` 추가)
- Create: `app/routers/alerts.py`
- Modify: `app/main.py`
- Test: `tests/test_alerts_api.py`

- [ ] **Step 1: 실패하는 API 테스트 작성**

`tests/test_alerts_api.py` 생성:

```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models import PriceAlert


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _real_alert():
    a = PriceAlert(asset_id=1, basis="ABSOLUTE", direction="ABOVE", value=250.0)
    a.alert_id = 1
    a.enabled = True
    a.is_triggered = False
    a.note = None
    return a


@pytest.mark.asyncio
async def test_create_rejects_nonpositive_value():
    async with await _client() as ac:
        resp = await ac.post("/api/alerts", json={
            "asset_id": 1, "basis": "ABSOLUTE", "direction": "ABOVE", "value": 0})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_bad_basis():
    async with await _client() as ac:
        resp = await ac.post("/api/alerts", json={
            "asset_id": 1, "basis": "NOPE", "direction": "ABOVE", "value": 1})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_purchase_avg_requires_holdings():
    asset = MagicMock(data_source="yfinance")
    with patch("app.db.AsyncSession.get", AsyncMock(return_value=asset)), \
         patch("app.routers.alerts.alert_store.has_holdings", AsyncMock(return_value=False)):
        async with await _client() as ac:
            resp = await ac.post("/api/alerts", json={
                "asset_id": 1, "basis": "PURCHASE_AVG", "direction": "BELOW", "value": 15})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_week52_rejects_manual():
    asset = MagicMock(data_source="manual")
    with patch("app.db.AsyncSession.get", AsyncMock(return_value=asset)):
        async with await _client() as ac:
            resp = await ac.post("/api/alerts", json={
                "asset_id": 1, "basis": "WEEK52_HIGH", "direction": "BELOW", "value": 10})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_absolute_ok():
    asset = MagicMock(data_source="yfinance")
    with patch("app.db.AsyncSession.get", AsyncMock(return_value=asset)), \
         patch("app.routers.alerts.alert_store.create_alert", AsyncMock(return_value=_real_alert())):
        async with await _client() as ac:
            resp = await ac.post("/api/alerts", json={
                "asset_id": 1, "basis": "ABSOLUTE", "direction": "ABOVE", "value": 250})
    assert resp.status_code == 200
    assert resp.json()["basis"] == "ABSOLUTE"


@pytest.mark.asyncio
async def test_list_uses_view():
    rows = [{"alert_id": 1, "asset_id": 1, "basis": "ABSOLUTE", "direction": "ABOVE",
             "value": 250.0, "enabled": True, "is_triggered": False, "note": None,
             "target_price": 250.0, "current_price": 251.0, "price_status": "ok", "fired": True}]
    with patch("app.routers.alerts.list_alerts_view", AsyncMock(return_value=rows)):
        async with await _client() as ac:
            resp = await ac.get("/api/alerts?asset_id=1")
    assert resp.status_code == 200
    assert resp.json()[0]["fired"] is True


@pytest.mark.asyncio
async def test_rearm_calls_store():
    with patch("app.routers.alerts.alert_store.get_alert", AsyncMock(return_value=_real_alert())), \
         patch("app.routers.alerts.alert_store.rearm_alert", AsyncMock(return_value=_real_alert())) as r:
        async with await _client() as ac:
            resp = await ac.post("/api/alerts/1/rearm")
    assert resp.status_code == 200
    r.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_404_when_missing():
    with patch("app.routers.alerts.alert_store.get_alert", AsyncMock(return_value=None)):
        async with await _client() as ac:
            resp = await ac.delete("/api/alerts/99")
    assert resp.status_code == 404
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_alerts_api.py -v`
Expected: FAIL — 404(라우터 미등록) / ModuleNotFound(`app.routers.alerts`)

- [ ] **Step 3: list_alerts_view 추가**

`app/services/alert/alert_store.py` 끝에 추가(상단 import는 그대로 두고 함수만 추가):

```python
from app.services.market.quote_service import get_quote
from app.services.alert.basis import resolve_basis_price
from app.services.alert.evaluator import compute_target, is_fired


async def list_alerts_view(db: AsyncSession, asset_id: int) -> list[dict]:
    """자산의 알림 + 라이브(현재가·목표가·발동여부) 계산. 자산 없으면 빈 리스트."""
    asset = await db.get(Asset, asset_id)
    if asset is None:
        return []
    alerts = await list_by_asset(db, asset_id)
    quote = await get_quote(asset)
    cur = quote.price if quote.status == "ok" else None
    out: list[dict] = []
    for a in alerts:
        bp = await resolve_basis_price(db, asset, a.basis)
        target = (compute_target(a.basis, a.direction, float(a.value), bp)
                  if (bp is not None or a.basis == "ABSOLUTE") else None)
        fired = bool(cur is not None and target is not None
                     and is_fired(a.direction, cur, target))
        out.append({
            "alert_id": a.alert_id, "asset_id": a.asset_id, "basis": a.basis,
            "direction": a.direction, "value": float(a.value), "enabled": a.enabled,
            "is_triggered": a.is_triggered, "note": a.note,
            "target_price": target, "current_price": cur,
            "price_status": quote.status, "fired": fired,
        })
    return out
```

- [ ] **Step 4: 라우터 구현 + 등록**

`app/routers/alerts.py` 생성:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Asset
from app.schemas.alert import AlertCreate, AlertUpdate, AlertOut
from app.services.alert import alert_store
from app.services.alert.alert_store import list_alerts_view

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.post("", response_model=AlertOut)
async def create(body: AlertCreate, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, body.asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    if body.basis == "PURCHASE_AVG" and not await alert_store.has_holdings(db, body.asset_id):
        raise HTTPException(422, "보유 종목에만 평균매입가 기준 알림을 설정할 수 있습니다.")
    if body.basis in ("WEEK52_HIGH", "WEEK52_LOW") and asset.data_source == "manual":
        raise HTTPException(422, "수동(manual) 자산은 52주 기준 알림을 설정할 수 없습니다.")
    return await alert_store.create_alert(
        db, body.asset_id, body.basis, body.direction, body.value, body.note)


@router.get("")
async def list_alerts(asset_id: int, db: AsyncSession = Depends(get_db)):
    return await list_alerts_view(db, asset_id)


@router.put("/{alert_id}", response_model=AlertOut)
async def update(alert_id: int, body: AlertUpdate, db: AsyncSession = Depends(get_db)):
    alert = await alert_store.get_alert(db, alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    data = body.model_dump(exclude_unset=True)
    return await alert_store.update_alert(
        db, alert,
        value=data.get("value"),
        direction=data.get("direction"),
        note=(data["note"] if "note" in data else alert_store._UNSET),
        enabled=data.get("enabled"),
    )


@router.post("/{alert_id}/rearm", response_model=AlertOut)
async def rearm(alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await alert_store.get_alert(db, alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    return await alert_store.rearm_alert(db, alert)


@router.delete("/{alert_id}")
async def delete(alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await alert_store.get_alert(db, alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    await alert_store.delete_alert(db, alert)
    return {"deleted": alert_id}
```

`app/main.py` line-12 import에 `alerts` 추가:

```python
from app.routers import assets, holdings, portfolio, fx, settings as settings_router, cash, charts, watchlist, alerts
```

`app/main.py` include 루프에 `alerts.router` 추가:

```python
for r in (assets.router, holdings.router, portfolio.router, fx.router, settings_router.router, cash.router, charts.router, watchlist.router, alerts.router):
    app.include_router(r)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_alerts_api.py -v`
Expected: PASS (8개)
Run: `.venv/bin/python -c "import app.main"` → 에러 없음

- [ ] **Step 6: 커밋**

```bash
git add app/services/alert/alert_store.py app/routers/alerts.py app/main.py tests/test_alerts_api.py
git commit -m "feat(alert): /api/alerts 라우터 + 라이브 뷰 + 등록"
```

---

### Task 9: 스케줄러 5분 잡 등록

**Files:**
- Modify: `app/services/scheduler/scheduler.py`
- Test: `tests/test_alert_dispatcher.py` (잡 등록 확인 테스트 추가)

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_alert_dispatcher.py` 끝에 추가:

```python
def test_scheduler_registers_alert_tick():
    from app.services.scheduler import scheduler as sched_mod
    # 깨끗한 상태에서 시작
    sched_mod.shutdown_scheduler()
    sched_mod.start_scheduler()
    try:
        s = sched_mod._scheduler
        ids = {job.id for job in s.get_jobs()}
        assert "dispatch_tick" in ids
        assert "alert_tick" in ids
    finally:
        sched_mod.shutdown_scheduler()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_alert_dispatcher.py::test_scheduler_registers_alert_tick -v`
Expected: FAIL — `assert 'alert_tick' in {'dispatch_tick'}`

- [ ] **Step 3: 잡 추가**

`app/services/scheduler/scheduler.py` 상단 import에 추가:

```python
from app.services.alert.alert_dispatcher import evaluate_tick as alert_evaluate_tick
```

`start_scheduler()`의 기존 `add_job(dispatch_tick, ...)` 아래에 추가:

```python
    _scheduler.add_job(alert_evaluate_tick, "interval", minutes=5, id="alert_tick",
                       replace_existing=True, max_instances=1, coalesce=True)
```

(로그 메시지의 문구는 자유. 예: `_log.info("스케줄러 시작(tick 1분 + 알림 5분)")`)

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_alert_dispatcher.py -v`
Expected: PASS (5개)

- [ ] **Step 5: 커밋**

```bash
git add app/services/scheduler/scheduler.py tests/test_alert_dispatcher.py
git commit -m "feat(alert): 스케줄러 5분 alert_tick 잡 등록"
```

---

### Task 10: 프론트 api.ts + 자산 상세 허브 알림 섹션

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/pages/AssetDetail.tsx`

- [ ] **Step 1: api.ts 함수·타입 추가**

`frontend/src/api.ts`의 `api` 객체 안(마지막 항목 뒤)에 추가:

```ts
  listAlerts: (assetId: number) => j<AlertView[]>(`/api/alerts?asset_id=${assetId}`),
  createAlert: (a: AlertCreate) => j("/api/alerts", { method: "POST", body: JSON.stringify(a) }),
  rearmAlert: (id: number) => j(`/api/alerts/${id}/rearm`, { method: "POST" }),
  deleteAlert: (id: number) => j(`/api/alerts/${id}`, { method: "DELETE" }),
```

파일 끝에 타입 추가:

```ts
export type AlertBasis = "ABSOLUTE" | "PURCHASE_AVG" | "WEEK52_HIGH" | "WEEK52_LOW";
export type AlertDirection = "ABOVE" | "BELOW";
export interface AlertCreate {
  asset_id: number; basis: AlertBasis; direction: AlertDirection; value: number; note?: string | null;
}
export interface AlertView {
  alert_id: number; asset_id: number; basis: AlertBasis; direction: AlertDirection;
  value: number; enabled: boolean; is_triggered: boolean; note: string | null;
  target_price: number | null; current_price: number | null; price_status: string; fired: boolean;
}
```

- [ ] **Step 2: AssetDetail에 알림 섹션 추가**

`frontend/src/pages/AssetDetail.tsx` 상단 import에 타입 추가(기존 `import type { AssetDetailOut } from "../api";`를 아래로 교체):

```tsx
import type { AssetDetailOut, AlertView, AlertBasis, AlertDirection } from "../api";
```

컴포넌트 함수 본문 안, 기존 state 선언들 아래에 알림 state 추가:

```tsx
  const [alerts, setAlerts] = useState<AlertView[]>([]);
  const [aBasis, setABasis] = useState<AlertBasis>("ABSOLUTE");
  const [aDir, setADir] = useState<AlertDirection>("ABOVE");
  const [aValue, setAValue] = useState("");
  const [aMsg, setAMsg] = useState("");
```

기존 `useEffect`(assetId 변경 시) 안에서 alerts도 로드하도록, 그 effect 본문 끝에 추가:

```tsx
    api.listAlerts(assetId).then(setAlerts).catch(() => setAlerts([]));
```

`src` 헬퍼 함수 정의 아래(또는 다른 핸들러들 사이)에 알림 핸들러 추가:

```tsx
  const BASIS_LABEL: Record<AlertBasis, string> = {
    ABSOLUTE: "절대 목표가", PURCHASE_AVG: "평균매입가 대비",
    WEEK52_HIGH: "52주 고점 대비", WEEK52_LOW: "52주 저점 대비",
  };
  const isManual = detail?.asset.data_source === "manual";
  const held = !!detail?.held;
  const basisDisabled = (b: AlertBasis) =>
    (b === "PURCHASE_AVG" && !held) || ((b === "WEEK52_HIGH" || b === "WEEK52_LOW") && isManual);

  const reloadAlerts = async () => { if (assetId) setAlerts(await api.listAlerts(assetId)); };
  const addAlert = async () => {
    if (!assetId) return;
    setAMsg("");
    try {
      await api.createAlert({ asset_id: assetId, basis: aBasis, direction: aDir, value: Number(aValue) });
      setAValue(""); await reloadAlerts();
    } catch (e: any) { setAMsg("추가 실패: " + e.message); }
  };
  const rearm = async (id: number) => {
    try { await api.rearmAlert(id); await reloadAlerts(); }
    catch (e: any) { setAMsg("재무장 실패: " + e.message); }
  };
  const delAlert = async (id: number) => {
    try { await api.deleteAlert(id); await reloadAlerts(); }
    catch (e: any) { setAMsg("삭제 실패: " + e.message); }
  };
  const valueUnit = aBasis === "ABSOLUTE" ? "가격" : "%";
```

JSX에서 차트 섹션 위(스케줄 박스 아래)에 알림 섹션 추가:

```tsx
      <div className="border rounded p-3 bg-white max-w-3xl space-y-3">
        <h2 className="font-semibold text-gray-700">가격 알림</h2>
        <div className="flex items-center gap-2 flex-wrap">
          <select className="border rounded px-2 py-1" value={aBasis}
            onChange={(e) => setABasis(e.target.value as AlertBasis)}>
            {(Object.keys(BASIS_LABEL) as AlertBasis[]).map((b) => (
              <option key={b} value={b} disabled={basisDisabled(b)}>{BASIS_LABEL[b]}</option>
            ))}
          </select>
          <select className="border rounded px-2 py-1" value={aDir}
            onChange={(e) => setADir(e.target.value as AlertDirection)}>
            <option value="ABOVE">이상 도달</option>
            <option value="BELOW">이하 도달</option>
          </select>
          <input className="border rounded px-2 py-1 w-28" placeholder={valueUnit}
            value={aValue} onChange={(e) => setAValue(e.target.value)} />
          <span className="text-xs text-gray-500">{valueUnit}</span>
          <button onClick={addAlert} className="px-3 py-1 rounded bg-blue-600 text-white">추가</button>
          {aMsg && <span className="text-sm text-gray-600">{aMsg}</span>}
        </div>
        <table className="w-full text-sm border-collapse">
          <thead><tr className="border-b text-left text-gray-500">
            <th className="py-1">기준</th><th>방향</th><th>값</th><th>현재 목표가</th><th>상태</th><th></th>
          </tr></thead>
          <tbody>
            {alerts.map((al) => (
              <tr key={al.alert_id} className="border-b">
                <td className="py-1">{BASIS_LABEL[al.basis]}</td>
                <td>{al.direction === "ABOVE" ? "이상" : "이하"}</td>
                <td>{al.value}{al.basis === "ABSOLUTE" ? "" : "%"}</td>
                <td>{al.target_price == null ? "—" : al.target_price.toLocaleString()}</td>
                <td>{al.is_triggered
                  ? <span className="text-gray-500">발동됨</span>
                  : <span className="text-emerald-600">활성</span>}</td>
                <td className="whitespace-nowrap">
                  {al.is_triggered && (
                    <button onClick={() => rearm(al.alert_id)} className="text-blue-600 mr-2">재무장</button>
                  )}
                  <button onClick={() => delAlert(al.alert_id)} className="text-red-600">삭제</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
```

- [ ] **Step 3: 빌드 확인**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: 타입 에러 없음, 빌드 성공

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/api.ts frontend/src/pages/AssetDetail.tsx
git commit -m "feat(alert): 자산 상세 허브에 가격 알림 섹션 + api 클라이언트"
```

---

### Task 11: 전체 검증

**Files:** 없음(검증만)

- [ ] **Step 1: 백엔드 전체 테스트(실 DB)**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q`
Expected: 신규 알림 테스트 포함 전부 PASS, 기존 테스트 회귀 없음

- [ ] **Step 2: 앱 import/부팅 스모크**

Run: `.venv/bin/python -c "import app.main"`
Expected: 에러 없음(라우터·스케줄러 잡 import 정합)

- [ ] **Step 3: 프론트 빌드**

Run: `cd frontend && npm run build`
Expected: 빌드 성공

- [ ] **Step 4: 수동 스모크(앱 실행 후 브라우저)**

- 포트폴리오/관심종목 → 자산 클릭 → 자산 상세 "가격 알림" 섹션 노출
- 관심(비보유) 자산: PURCHASE_AVG 옵션 비활성, manual 자산: WEEK52 옵션 비활성
- ABSOLUTE 알림 추가 → 목록에 활성으로 등장, 현재 목표가 표시
- (가능하면) 조건 충족 종목으로 5분 tick 후 텔레그램 수신 + 목록 "발동됨" → 재무장 동작
- 삭제 동작

---

## Self-Review (작성자 점검 결과)

- **스펙 커버리지**: 모델(T1)·evaluator(T2)·message(T3)·market_hours(T4)·basis+WEEK52캐시(T5)·store+스키마(T6)·디스패처(T7)·라우터+라이브뷰+검증(T8)·5분 잡(T9)·프론트 섹션(T10)·검증(T11). spec의 모든 섹션 대응. 비목표(REFERENCE·전역페이지·사용자주기·쿨다운)는 미구현 유지.
- **Placeholder 스캔**: 모든 코드/명령 스텝에 실제 내용 포함. TBD 없음.
- **타입 일관성**: `compute_target(basis,direction,value,basis_price)`/`is_fired(direction,current,target)`/`resolve_basis_price(db,asset,basis)`/`build_message(asset,alert,current,target)`/store 함수 시그니처가 디스패처·라우터·테스트 전반에서 일치. 라우터의 `note` 미설정 처리에 `alert_store._UNSET` 사용(store와 동일 sentinel). 프론트 `AlertView`/`AlertCreate` 키가 백엔드 `list_alerts_view`/`AlertCreate` 키와 일치.
- **디스패처 테스트**: SessionLocal·외부 의존성을 전부 patch해 DB 없이 검증 가능(발동·장마감 skip·시세실패 skip·자산당 quote 1회). 그룹화 튜플 `setdefault(asset_id,(asset,[]))[1].append(...)` 패턴 검증됨.
