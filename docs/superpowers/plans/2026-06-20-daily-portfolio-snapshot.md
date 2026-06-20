# 일별 자산추세 스냅샷 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매일 포트폴리오 레벨 스냅샷(총자산·원가·평가손익·현금 + 자산군별)을 시계열로 적재하고, 대시보드에서 총자산 추세를 SVG 라인차트로 보여준다.

**Architecture:** 신규 `portfolio_snapshots` 테이블에 `get_portfolio()` 결과를 매일 KST 06:30 고정 cron으로 date-멱등 upsert. `GET /api/trend?period=...`로 조회하고, 프론트는 의존성 0의 자체 SVG 컴포넌트로 렌더. 순수함수(`build_snapshot_row`, `period_to_since`)와 store/orchestration을 분리해 테스트 용이성 확보.

**Tech Stack:** FastAPI · async SQLAlchemy 2.0 · asyncpg · PostgreSQL(JSONB) · APScheduler · React 19 + Vite + TS + Tailwind.

설계 문서: `docs/superpowers/specs/2026-06-20-daily-portfolio-snapshot-design.md`

**테스트 실행 커맨드(공통):**
```bash
SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q
```
순수함수 테스트는 DB 불필요하나 위 커맨드로 함께 실행됨(통합 테스트는 TEST_DATABASE_URL 없으면 skip).

---

## Task 1: `PortfolioSnapshot` 모델 + 등록

**Files:**
- Create: `app/models/portfolio_snapshot.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_portfolio_snapshot_store.py` (이 태스크에선 모델 왕복만)

- [ ] **Step 1: 모델 작성**

Create `app/models/portfolio_snapshot.py`:

```python
from datetime import datetime, date
from sqlalchemy import Numeric, Date, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    total_value_krw: Mapped[float] = mapped_column(Numeric, nullable=False)
    total_cost_krw: Mapped[float] = mapped_column(Numeric, nullable=False)
    total_pl_krw: Mapped[float] = mapped_column(Numeric, nullable=False)
    total_cash_krw: Mapped[float] = mapped_column(Numeric, nullable=False)
    allocation: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: `__init__.py`에 등록**

Modify `app/models/__init__.py` — import와 `__all__`에 `PortfolioSnapshot` 추가:

```python
from app.models.asset import Asset
from app.models.exchange_rate import ExchangeRate
from app.models.price_snapshot import PriceSnapshot
from app.models.holding import Holding
from app.models.app_setting import AppSetting
from app.models.cash_balance import CashBalance
from app.models.schedule import Schedule
from app.models.price_alert import PriceAlert
from app.models.portfolio_snapshot import PortfolioSnapshot

__all__ = ["Asset", "ExchangeRate", "PriceSnapshot", "Holding", "AppSetting",
           "CashBalance", "Schedule", "PriceAlert", "PortfolioSnapshot"]
```

- [ ] **Step 3: 실패 테스트 작성(모델 왕복)**

Create `tests/test_portfolio_snapshot_store.py`:

```python
from datetime import date
import pytest
from app.models import PortfolioSnapshot


@pytest.mark.asyncio
async def test_insert_and_read_snapshot(db_session):
    snap = PortfolioSnapshot(
        date=date(2026, 6, 20),
        total_value_krw=1000, total_cost_krw=800,
        total_pl_krw=200, total_cash_krw=100,
        allocation=[{"asset_class": "주식", "value_krw": 900}],
    )
    db_session.add(snap)
    await db_session.commit()
    assert snap.id is not None
    assert snap.allocation[0]["asset_class"] == "주식"
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run:
```bash
SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_portfolio_snapshot_store.py -v
```
Expected: PASS (conftest가 invest_test 스키마에 테이블을 drop/create하므로 신규 테이블 자동 생성).

- [ ] **Step 5: 커밋**

```bash
git add app/models/portfolio_snapshot.py app/models/__init__.py tests/test_portfolio_snapshot_store.py
git commit -m "feat(snapshot): PortfolioSnapshot 모델 + 등록"
```

---

## Task 2: `build_snapshot_row` 순수함수

**Files:**
- Create: `app/services/snapshot/__init__.py` (빈 파일)
- Create: `app/services/snapshot/snapshot_service.py`
- Test: `tests/test_snapshot_service.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_snapshot_service.py`:

```python
from datetime import date
from app.services.snapshot.snapshot_service import build_snapshot_row


def test_build_snapshot_row_maps_summary_and_allocation():
    portfolio = {
        "summary": {
            "total_value_krw": 1500.0,
            "total_cost_krw": 1200.0,
            "total_profit_loss_krw": 250.0,
            "total_profit_loss_pct": 20.8,
            "total_cash_krw": 300.0,
        },
        "allocation": [
            {"asset_class": "주식", "value_krw": 900.0, "weight_pct": 60.0},
            {"asset_class": "현금성", "value_krw": 300.0, "weight_pct": 20.0},
        ],
    }
    row = build_snapshot_row(portfolio, date(2026, 6, 20))
    assert row["date"] == date(2026, 6, 20)
    assert row["total_value_krw"] == 1500.0
    assert row["total_cost_krw"] == 1200.0
    assert row["total_pl_krw"] == 250.0
    assert row["total_cash_krw"] == 300.0
    # allocation은 asset_class/value_krw만 남긴다(weight_pct 제외)
    assert row["allocation"] == [
        {"asset_class": "주식", "value_krw": 900.0},
        {"asset_class": "현금성", "value_krw": 300.0},
    ]
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run:
```bash
.venv/bin/pytest tests/test_snapshot_service.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.snapshot'`.

- [ ] **Step 3: 최소 구현**

Create `app/services/snapshot/__init__.py` (빈 파일).

Create `app/services/snapshot/snapshot_service.py`:

```python
"""일별 포트폴리오 스냅샷: get_portfolio 결과를 테이블 행으로 변환·적재한다."""
from datetime import date


def build_snapshot_row(portfolio: dict, today: date) -> dict:
    """get_portfolio() 반환 dict + 날짜 → portfolio_snapshots 컬럼 dict(순수)."""
    s = portfolio["summary"]
    return {
        "date": today,
        "total_value_krw": s["total_value_krw"],
        "total_cost_krw": s["total_cost_krw"],
        "total_pl_krw": s["total_profit_loss_krw"],
        "total_cash_krw": s["total_cash_krw"],
        "allocation": [
            {"asset_class": a["asset_class"], "value_krw": a["value_krw"]}
            for a in portfolio["allocation"]
        ],
    }
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run:
```bash
.venv/bin/pytest tests/test_snapshot_service.py -v
```
Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add app/services/snapshot/__init__.py app/services/snapshot/snapshot_service.py tests/test_snapshot_service.py
git commit -m "feat(snapshot): build_snapshot_row 순수함수"
```

---

## Task 3: `snapshot_store` (upsert + list)

**Files:**
- Create: `app/services/snapshot/snapshot_store.py`
- Test: `tests/test_portfolio_snapshot_store.py` (Task 1 파일에 추가)

- [ ] **Step 1: 실패 테스트 추가**

Append to `tests/test_portfolio_snapshot_store.py`:

```python
from app.services.snapshot import snapshot_store


def _row(d: date, value: float):
    return {"date": d, "total_value_krw": value, "total_cost_krw": value,
            "total_pl_krw": 0, "total_cash_krw": 0,
            "allocation": [{"asset_class": "주식", "value_krw": value}]}


@pytest.mark.asyncio
async def test_upsert_is_idempotent_by_date(db_session):
    await snapshot_store.upsert_snapshot(db_session, _row(date(2026, 6, 20), 1000))
    # 같은 날짜 재적재 → 행 추가 없이 값 갱신
    snap = await snapshot_store.upsert_snapshot(db_session, _row(date(2026, 6, 20), 1234))
    rows = await snapshot_store.list_snapshots(db_session, None)
    assert len(rows) == 1
    assert float(snap.total_value_krw) == 1234


@pytest.mark.asyncio
async def test_list_snapshots_since_filter_and_order(db_session):
    await snapshot_store.upsert_snapshot(db_session, _row(date(2026, 6, 10), 1))
    await snapshot_store.upsert_snapshot(db_session, _row(date(2026, 6, 20), 2))
    await snapshot_store.upsert_snapshot(db_session, _row(date(2026, 6, 15), 3))
    rows = await snapshot_store.list_snapshots(db_session, date(2026, 6, 15))
    assert [r.date for r in rows] == [date(2026, 6, 15), date(2026, 6, 20)]  # since 필터 + 오름차순
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run:
```bash
SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_portfolio_snapshot_store.py -v
```
Expected: FAIL — `ImportError: cannot import name 'snapshot_store'`.

- [ ] **Step 3: 최소 구현**

Create `app/services/snapshot/snapshot_store.py`:

```python
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import PortfolioSnapshot


async def upsert_snapshot(db: AsyncSession, row: dict) -> PortfolioSnapshot:
    """date 기준 upsert. 같은 날짜 행이 있으면 값만 갱신(멱등)."""
    snap = (await db.execute(
        select(PortfolioSnapshot).where(PortfolioSnapshot.date == row["date"])
    )).scalar_one_or_none()
    if snap is None:
        snap = PortfolioSnapshot(date=row["date"])
        db.add(snap)
    snap.total_value_krw = row["total_value_krw"]
    snap.total_cost_krw = row["total_cost_krw"]
    snap.total_pl_krw = row["total_pl_krw"]
    snap.total_cash_krw = row["total_cash_krw"]
    snap.allocation = row["allocation"]
    await db.commit()
    await db.refresh(snap)
    return snap


async def list_snapshots(db: AsyncSession, since: date | None) -> list[PortfolioSnapshot]:
    """since 이상 날짜를 오름차순으로. since=None이면 전체."""
    stmt = select(PortfolioSnapshot).order_by(PortfolioSnapshot.date.asc())
    if since is not None:
        stmt = stmt.where(PortfolioSnapshot.date >= since)
    return list((await db.execute(stmt)).scalars().all())
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run:
```bash
SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_portfolio_snapshot_store.py -v
```
Expected: 3 passed.

- [ ] **Step 5: 커밋**

```bash
git add app/services/snapshot/snapshot_store.py tests/test_portfolio_snapshot_store.py
git commit -m "feat(snapshot): snapshot_store upsert/list (date 멱등)"
```

---

## Task 4: `capture_daily_snapshot` + `snapshot_tick` 오케스트레이션

**Files:**
- Modify: `app/services/snapshot/snapshot_service.py`
- Test: `tests/test_snapshot_service.py` (추가)

- [ ] **Step 1: 실패 테스트 추가(빈 포트폴리오 엔드투엔드)**

Append to `tests/test_snapshot_service.py`:

```python
import pytest
from datetime import date as _date
from app.services.snapshot import snapshot_service, snapshot_store


@pytest.mark.asyncio
async def test_capture_daily_snapshot_empty_portfolio(db_session):
    # 보유/현금 없는 빈 포트폴리오 → 0값 행 1개 기록(네트워크 호출 없음)
    snap = await snapshot_service.capture_daily_snapshot(db_session)
    assert snap.id is not None
    assert float(snap.total_value_krw) == 0
    rows = await snapshot_store.list_snapshots(db_session, None)
    assert len(rows) == 1
    assert rows[0].date == _date.today()  # 주: 서버가 KST면 today와 동일. UTC 환경에선 ±1일 가능 — KST 기준이 정상.
```

참고: `capture_daily_snapshot`은 KST 날짜를 쓴다. 테스트 러너가 KST가 아니면 날짜가 어긋날 수 있으나, 운영(Asia/Seoul) 기준이 정상이다. 환경이 UTC라 이 단언이 깨지면 `rows[0].date`를 `snap.date`와 비교하도록 바꾼다.

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run:
```bash
SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_snapshot_service.py -v
```
Expected: FAIL — `AttributeError: module ... has no attribute 'capture_daily_snapshot'`.

- [ ] **Step 3: 구현 추가**

Append to `app/services/snapshot/snapshot_service.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import SessionLocal
from app.models import PortfolioSnapshot
from app.services.portfolio.portfolio_service import get_portfolio
from app.services.snapshot import snapshot_store

_KST = ZoneInfo("Asia/Seoul")


async def capture_daily_snapshot(db: AsyncSession) -> PortfolioSnapshot:
    """현재 포트폴리오를 오늘(KST) 스냅샷으로 적재(멱등)."""
    portfolio = await get_portfolio(db)
    today = datetime.now(_KST).date()
    row = build_snapshot_row(portfolio, today)
    return await snapshot_store.upsert_snapshot(db, row)


async def snapshot_tick() -> None:
    """스케줄러 콜백: 자체 세션을 열어 1회 적재."""
    async with SessionLocal() as db:
        await capture_daily_snapshot(db)
```

주의: `snapshot_service.py` 상단에 이미 `from datetime import date`가 있다. 위 블록의 `from datetime import datetime`은 별도 줄로 추가하거나 상단 import를 `from datetime import date, datetime`으로 합친다(중복 import 피하기).

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run:
```bash
SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_snapshot_service.py -v
```
Expected: 2 passed (build_snapshot_row + capture empty). KST/UTC 어긋나면 Step 1 참고대로 단언 수정.

- [ ] **Step 5: 커밋**

```bash
git add app/services/snapshot/snapshot_service.py tests/test_snapshot_service.py
git commit -m "feat(snapshot): capture_daily_snapshot + snapshot_tick"
```

---

## Task 5: 스케줄러 cron 잡 등록

**Files:**
- Modify: `app/services/scheduler/scheduler.py`

테스트 노트: 기존 스케줄러도 단위 테스트가 없다(앱 lifespan에서만 기동). 이 태스크는 등록 코드만 추가하고, 실제 발동은 Task 8(스모크)에서 확인한다.

- [ ] **Step 1: import 추가**

Modify `app/services/scheduler/scheduler.py` — 상단 import 블록에 추가:

```python
from app.services.snapshot.snapshot_service import snapshot_tick
```

- [ ] **Step 2: cron 잡 등록**

`start_scheduler()` 안 `alert_tick` 잡 등록 직후에 추가:

```python
    _scheduler.add_job(snapshot_tick, "cron", hour=6, minute=30, id="daily_snapshot",
                       replace_existing=True, max_instances=1, coalesce=True)
```

그리고 마지막 로그 문구를 갱신:

```python
    _log.info("스케줄러 시작(tick 1분 + 알림 5분 + 스냅샷 매일 06:30)")
```

- [ ] **Step 3: import 정합성 확인(앱 임포트 깨지지 않는지)**

Run:
```bash
.venv/bin/python -c "from app.services.scheduler.scheduler import start_scheduler; print('ok')"
```
Expected: `ok` (순환 import·오타 없음 확인).

- [ ] **Step 4: 커밋**

```bash
git add app/services/scheduler/scheduler.py
git commit -m "feat(snapshot): 매일 06:30 KST cron 잡 등록"
```

---

## Task 6: `period_to_since` 순수함수 + `GET /api/trend` 라우터

**Files:**
- Create: `app/routers/trend.py`
- Modify: `app/main.py`
- Test: `tests/test_trend_api.py`

- [ ] **Step 1: 실패 테스트 작성(순수함수 + 라우터)**

Create `tests/test_trend_api.py`:

```python
from datetime import date
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.routers.trend import period_to_since


def test_period_to_since_known_periods():
    today = date(2026, 6, 20)
    assert period_to_since("1M", today) == date(2026, 5, 21)
    assert period_to_since("3M", today) == date(2026, 3, 22)
    assert period_to_since("1Y", today) == date(2025, 6, 20)
    assert period_to_since("ALL", today) is None
    # 미지/누락 → 1M 폴백
    assert period_to_since("XX", today) == date(2026, 5, 21)


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_trend_returns_serialized_rows():
    class _Snap:
        date = date(2026, 6, 20)
        total_value_krw = 1500
        total_cost_krw = 1200
        total_pl_krw = 300
        total_cash_krw = 100
        allocation = [{"asset_class": "주식", "value_krw": 1400}]
    with patch("app.routers.trend.snapshot_store.list_snapshots",
               AsyncMock(return_value=[_Snap()])):
        async with await _client() as ac:
            resp = await ac.get("/api/trend?period=1M")
    assert resp.status_code == 200
    body = resp.json()
    assert body == [{
        "date": "2026-06-20",
        "total_value_krw": 1500.0,
        "total_cost_krw": 1200.0,
        "total_pl_krw": 300.0,
        "total_cash_krw": 100.0,
        "allocation": [{"asset_class": "주식", "value_krw": 1400}],
    }]
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run:
```bash
.venv/bin/pytest tests/test_trend_api.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.trend'`.

- [ ] **Step 3: 라우터 구현**

Create `app/routers/trend.py`:

```python
from datetime import date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.services.snapshot import snapshot_store

router = APIRouter(prefix="/api/trend", tags=["trend"])

_DAYS = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}


def period_to_since(period: str, today: date) -> date | None:
    """기간 문자열 → 시작일. ALL=None, 미지/누락=1M(30일) 폴백."""
    if period == "ALL":
        return None
    return today - timedelta(days=_DAYS.get(period, 30))


@router.get("")
async def trend(period: str = "1M", db: AsyncSession = Depends(get_db)):
    since = period_to_since(period, date.today())
    rows = await snapshot_store.list_snapshots(db, since)
    return [
        {
            "date": r.date.isoformat(),
            "total_value_krw": float(r.total_value_krw),
            "total_cost_krw": float(r.total_cost_krw),
            "total_pl_krw": float(r.total_pl_krw),
            "total_cash_krw": float(r.total_cash_krw),
            "allocation": r.allocation,
        }
        for r in rows
    ]
```

- [ ] **Step 4: `main.py`에 라우터 등록**

Modify `app/main.py`:

import 줄에 `trend` 추가:
```python
from app.routers import assets, holdings, portfolio, fx, settings as settings_router, cash, charts, watchlist, alerts, market_summary, trend
```

`include_router` 루프 튜플 끝에 `trend.router` 추가:
```python
for r in (assets.router, holdings.router, portfolio.router, fx.router, settings_router.router, cash.router, charts.router, watchlist.router, alerts.router, market_summary.router, trend.router):
    app.include_router(r)
```

- [ ] **Step 5: 테스트 실행 → 통과 확인**

Run:
```bash
.venv/bin/pytest tests/test_trend_api.py -v
```
Expected: 2 passed.

- [ ] **Step 6: 커밋**

```bash
git add app/routers/trend.py app/main.py tests/test_trend_api.py
git commit -m "feat(snapshot): GET /api/trend + period_to_since"
```

---

## Task 7: 프론트 — `getTrend` API + `TrendChart` + 대시보드 통합

**Files:**
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/components/TrendChart.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: API 클라이언트에 타입 + 메서드 추가**

Modify `frontend/src/api.ts`:

`AllocationSlice` 인터페이스 근처(다른 `export interface`들과 같은 영역)에 타입 추가:
```typescript
export interface TrendPoint {
  date: string;
  total_value_krw: number;
  total_cost_krw: number;
  total_pl_krw: number;
  total_cash_krw: number;
  allocation: { asset_class: string; value_krw: number }[];
}
```

`api` 객체에 메서드 추가(기존 항목들과 같은 형식, 예: `listAllAlerts` 줄 근처):
```typescript
  getTrend: (period: string) => j<TrendPoint[]>(`/api/trend?period=${period}`),
```

- [ ] **Step 2: `TrendChart` 컴포넌트 작성**

Create `frontend/src/components/TrendChart.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api } from "../api";
import type { TrendPoint } from "../api";

const PERIODS = ["1M", "3M", "6M", "1Y", "ALL"] as const;
type Period = (typeof PERIODS)[number];

const krw = (v: number) => "₩" + Math.round(v).toLocaleString("ko-KR");

export default function TrendChart() {
  const [period, setPeriod] = useState<Period>("1M");
  const [data, setData] = useState<TrendPoint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.getTrend(period)
      .then(setData)
      .catch(() => setData([]))
      .finally(() => setLoading(false));
  }, [period]);

  const W = 600, H = 180, PAD = 10;
  const values = data.map((d) => d.total_value_krw);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 1;
  const span = max - min || 1;
  const n = data.length;
  const px = (i: number) => (n <= 1 ? W / 2 : PAD + (i * (W - 2 * PAD)) / (n - 1));
  const py = (v: number) => H - PAD - ((v - min) / span) * (H - 2 * PAD);
  const points = data.map((d, i) => `${px(i)},${py(d.total_value_krw)}`).join(" ");

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <h2 className="font-semibold">자산 추세</h2>
        <div className="flex gap-1">
          {PERIODS.map((p) => (
            <button key={p} onClick={() => setPeriod(p)}
              className={`badge ${p === period ? "btn-primary" : ""}`}>{p}</button>
          ))}
        </div>
      </div>
      {loading ? (
        <p className="text-sm text-muted">불러오는 중…</p>
      ) : data.length < 2 ? (
        <p className="text-sm text-muted">스냅샷이 충분히 쌓이면 추세가 표시됩니다.</p>
      ) : (
        <>
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
            <polyline fill="none" stroke="var(--accent)" strokeWidth={2} points={points} />
            {data.map((d, i) => (
              <circle key={d.date} cx={px(i)} cy={py(d.total_value_krw)} r={2.5} fill="var(--accent)">
                <title>{d.date} · {krw(d.total_value_krw)}</title>
              </circle>
            ))}
          </svg>
          <div className="flex justify-between text-xs text-muted mt-1">
            <span>{data[0].date}</span>
            <span>최신 {krw(data[data.length - 1].total_value_krw)}</span>
            <span>{data[data.length - 1].date}</span>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3: 대시보드에 삽입**

Modify `frontend/src/pages/Dashboard.tsx`:

상단 import에 추가:
```tsx
import TrendChart from "../components/TrendChart";
```

요약 카드 grid(`</div>`로 닫히는 `grid grid-cols-1 sm:grid-cols-3 ...` 블록)와 그 아래 포지션 테이블 `<div className="overflow-x-auto">` 사이에 컴포넌트 추가. 즉 요약 grid를 닫는 `</div>` 다음 줄에:
```tsx
      <TrendChart />
```

- [ ] **Step 4: 빌드 + 타입체크**

Run:
```bash
cd frontend && npm run build
```
Expected: 성공(타입 에러 0). `tsc`가 build에 포함됨(기존 관례).

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/api.ts frontend/src/components/TrendChart.tsx frontend/src/pages/Dashboard.tsx
git commit -m "feat(snapshot): 대시보드 자산추세 SVG 차트 + getTrend"
```

---

## Task 8: 전체 테스트 + 실 스모크(사용자 확인)

**Files:** 없음(검증).

- [ ] **Step 1: 백엔드 전체 테스트**

Run:
```bash
SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q
```
Expected: 기존 통과 수(직전 170대) + 신규(모델 1 + service 2 + store 2 + trend 3 = 8) 전부 passed. 회귀 0.

- [ ] **Step 2: 프론트 빌드 재확인**

Run:
```bash
cd frontend && npm run build
```
Expected: 성공.

- [ ] **Step 3: 실 적재 스모크(사용자와 함께)**

옵션 A(권장): 일시적으로 cron을 가까운 시각으로 바꿔 1회 적재 확인 후 06:30 환원.
옵션 B: 직접 1회 적재 — 운영 `invest` 스키마에 실제 행이 생기므로 **사용자 동의 후** 실행:
```bash
.venv/bin/python -c "import asyncio; from app.services.snapshot.snapshot_service import snapshot_tick; asyncio.run(snapshot_tick())"
```
(`snapshot_tick`이 자체 세션을 열어 오늘 날짜 1행을 upsert한다. 적재 없이 조회만 보려면 앱을 켠 상태에서 `GET /api/trend?period=ALL`로 빈 배열을 확인한다.)

확인 항목: `GET /api/trend?period=ALL`이 200 + 배열 반환, 대시보드에 "자산 추세" 카드가 보이고 스냅샷 2개 미만이면 안내문구가 뜬다.

- [ ] **Step 4: ROADMAP 갱신 + 커밋**

`docs/superpowers/ROADMAP.md`의 "## 3단계" 섹션에 A(일별 스냅샷) 구현 완료를 반영(merge 커밋 해시, 테스트 수). 그리고:
```bash
git add docs/superpowers/ROADMAP.md
git commit -m "docs(roadmap): 일별 자산추세 스냅샷(3단계 A) 완료 반영"
```

---

## Self-Review 메모(작성자 확인 완료)

- **Spec 커버리지:** 모델(T1)·적재 cron(T4·T5)·`build_snapshot_row`/`period_to_since` 순수함수(T2·T6)·store(T3)·`GET /api/trend`(T6)·대시보드 SVG 차트(T7)·테스트/스모크(T8) — spec 1~7장 전부 태스크에 매핑됨. 비목표(백필·스택차트·시각설정 UI)는 의도적으로 태스크 없음.
- **타입 정합성:** `build_snapshot_row`→`upsert_snapshot`→`PortfolioSnapshot` 컬럼명(`total_pl_krw` 등) 전 태스크 일치. `get_portfolio()` summary 키는 `total_profit_loss_krw`(원본) → 행에선 `total_pl_krw`로 매핑(T2 테스트가 보장). `TrendPoint`/`getTrend`/`/api/trend` 응답 키 일치.
- **플레이스홀더:** 없음. 모든 코드/커맨드/기대출력 명시.
- **알려진 환경 주의:** capture 테스트의 `date.today()` vs KST(T4 Step1에 대안 단언 명시). 스모크는 운영 스키마 영향이라 사용자 동의 게이트(T8 Step3).
