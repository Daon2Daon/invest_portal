# 2d 스케줄 자동 발송 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목별로 설정한 시각·요일에 차트(+AI 분석)를 텔레그램으로 자동 발송한다.

**Architecture:** 단일 `schedules` 테이블 + 1분 간격 APScheduler tick 잡 1개가 due한 스케줄을 순차 발송하는 중앙 디스패처. 발송 로직은 기존 send-telegram 라우트에서 추출한 `chart_dispatch.send_chart_telegram`을 수동·자동이 공유.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, asyncpg, APScheduler(AsyncIOScheduler, 메모리 잡스토어), React/Vite/TS.

**Spec:** `docs/superpowers/specs/2026-06-16-scheduled-auto-send-design.md`

**테스트 실행(항상 이 env로):**
```
SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q
```

---

## File Structure

- 신규 `app/models/schedule.py` — Schedule ORM 모델(`schedules` 테이블).
- 수정 `app/models/__init__.py` — Schedule export(ensure_schema가 자동 생성).
- 신규 `app/services/scheduler/__init__.py` — 빈 패키지.
- 신규 `app/services/scheduler/schedule_store.py` — 스케줄 CRUD(DB).
- 신규 `app/services/scheduler/handlers.py` — feature_type별 핸들러 + 레지스트리.
- 신규 `app/services/scheduler/dispatcher.py` — `_is_due` 순수함수 + `dispatch_tick`.
- 신규 `app/services/scheduler/scheduler.py` — AsyncIOScheduler 래퍼(start/shutdown).
- 신규 `app/services/chart/chart_builder.py` — `build_png`(라우터 `_build_png`에서 추출, 도메인 예외).
- 신규 `app/services/notification/chart_dispatch.py` — `send_chart_telegram`(send-telegram 로직 추출).
- 수정 `app/routers/charts.py` — `_build_png`/`send_telegram` 라우트를 추출 함수 래퍼로 축소 + 스케줄 CRUD API.
- 수정 `app/main.py` — lifespan에 start/shutdown_scheduler.
- 수정 `requirements.txt` — apscheduler 추가.
- 신규 `tests/test_schedule_store.py`, `tests/test_scheduler_dispatcher.py`, `tests/test_charts_schedule.py`.
- 수정 `tests/test_charts_analyze.py` — send-telegram 테스트 patch 경로 갱신.
- 수정 `frontend/src/pages/Charts.tsx`, `frontend/src/api.ts`.

---

## Task 1: 의존성 + Schedule 모델

**Files:**
- Modify: `requirements.txt`
- Create: `app/models/schedule.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_schedule_store.py` (이 태스크에선 테이블 생성만 검증)

- [ ] **Step 1: apscheduler 의존성 추가 및 설치**

`requirements.txt` 끝에 한 줄 추가:
```
apscheduler>=3.10.0
```
Run: `.venv/bin/pip install "apscheduler>=3.10.0"`
Expected: `Successfully installed apscheduler-3.x ...` (또는 already satisfied)

- [ ] **Step 2: Schedule 모델 작성**

Create `app/models/schedule.py`:
```python
from datetime import datetime, date
from sqlalchemy import String, Boolean, Integer, Date, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class Schedule(Base):
    __tablename__ = "schedules"
    __table_args__ = (
        UniqueConstraint("feature_type", "target_id", name="uq_schedules_feature_target"),
    )

    schedule_id: Mapped[int] = mapped_column(primary_key=True)
    feature_type: Mapped[str] = mapped_column(String, nullable=False)   # 예: "chart_analysis"
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)     # chart_analysis면 asset_id
    send_time: Mapped[str] = mapped_column(String, nullable=False)      # "HH:MM" KST 벽시계
    days_of_week: Mapped[str] = mapped_column(String, nullable=False)   # "0,1,2,3,4" (월=0…일=6)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_date: Mapped[date | None] = mapped_column(Date)            # 마지막 발송 KST 날짜
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 3: 모델 export**

Modify `app/models/__init__.py` — import/__all__에 Schedule 추가:
```python
from app.models.asset import Asset
from app.models.exchange_rate import ExchangeRate
from app.models.price_snapshot import PriceSnapshot
from app.models.holding import Holding
from app.models.app_setting import AppSetting
from app.models.cash_balance import CashBalance
from app.models.schedule import Schedule

__all__ = ["Asset", "ExchangeRate", "PriceSnapshot", "Holding", "AppSetting", "CashBalance", "Schedule"]
```

- [ ] **Step 4: 테이블 생성 검증 테스트 작성**

Create `tests/test_schedule_store.py`:
```python
import pytest
from sqlalchemy import select
from app.models import Schedule


@pytest.mark.asyncio
async def test_schedules_table_created(db_session):
    # db_session fixture가 create_all 하므로 빈 조회가 에러 없이 동작하면 테이블 생성됨
    rows = (await db_session.execute(select(Schedule))).scalars().all()
    assert rows == []
```

- [ ] **Step 5: 테스트 실행(통과 확인)**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_schedule_store.py -q`
Expected: PASS (1 passed)

- [ ] **Step 6: 커밋**

```bash
git add requirements.txt app/models/schedule.py app/models/__init__.py tests/test_schedule_store.py
git commit -m "feat(2d): Schedule model + schedules table + apscheduler dep"
```

---

## Task 2: 스케줄 저장소(schedule_store)

**Files:**
- Create: `app/services/scheduler/__init__.py`
- Create: `app/services/scheduler/schedule_store.py`
- Test: `tests/test_schedule_store.py` (Task 1 파일에 추가)

- [ ] **Step 1: 패키지 init 생성**

Create `app/services/scheduler/__init__.py` (빈 파일):
```python
```

- [ ] **Step 2: 실패 테스트 작성**

`tests/test_schedule_store.py`에 추가:
```python
from app.services.scheduler import schedule_store as store
from app.services.scheduler.schedule_store import FEATURE_CHART


@pytest.mark.asyncio
async def test_upsert_creates_then_updates(db_session):
    s1 = await store.upsert_schedule(db_session, FEATURE_CHART, 1, "08:30", "0,1,2", True)
    assert s1.schedule_id is not None
    assert s1.send_time == "08:30"
    # 같은 (feature,target) 재호출 → update(중복 생성 X, UNIQUE)
    s2 = await store.upsert_schedule(db_session, FEATURE_CHART, 1, "09:00", "0,1,2,3,4", False)
    assert s2.schedule_id == s1.schedule_id
    assert s2.send_time == "09:00"
    assert s2.enabled is False
    all_rows = await store.list_enabled(db_session)
    assert all_rows == []  # enabled=False라 비활성 목록엔 없음


@pytest.mark.asyncio
async def test_get_and_delete(db_session):
    await store.upsert_schedule(db_session, FEATURE_CHART, 2, "10:00", "5,6", True)
    got = await store.get_schedule(db_session, FEATURE_CHART, 2)
    assert got is not None and got.target_id == 2
    assert await store.delete_schedule(db_session, FEATURE_CHART, 2) is True
    assert await store.get_schedule(db_session, FEATURE_CHART, 2) is None
    assert await store.delete_schedule(db_session, FEATURE_CHART, 2) is False  # 이미 없음


@pytest.mark.asyncio
async def test_list_enabled_only_returns_enabled(db_session):
    await store.upsert_schedule(db_session, FEATURE_CHART, 3, "08:00", "0", True)
    await store.upsert_schedule(db_session, FEATURE_CHART, 4, "08:00", "0", False)
    enabled = await store.list_enabled(db_session)
    targets = {s.target_id for s in enabled}
    assert 3 in targets and 4 not in targets
```

- [ ] **Step 3: 테스트 실행(실패 확인)**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_schedule_store.py -q`
Expected: FAIL (`ModuleNotFoundError` / `cannot import name 'schedule_store'`)

- [ ] **Step 4: schedule_store 구현**

Create `app/services/scheduler/schedule_store.py`:
```python
"""schedules 테이블 CRUD. 라우터·디스패처가 공유한다."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Schedule

FEATURE_CHART = "chart_analysis"


async def get_schedule(db: AsyncSession, feature_type: str, target_id: int) -> Schedule | None:
    res = await db.execute(
        select(Schedule).where(
            Schedule.feature_type == feature_type,
            Schedule.target_id == target_id,
        )
    )
    return res.scalar_one_or_none()


async def upsert_schedule(db: AsyncSession, feature_type: str, target_id: int,
                          send_time: str, days_of_week: str, enabled: bool) -> Schedule:
    sched = await get_schedule(db, feature_type, target_id)
    if sched is None:
        sched = Schedule(feature_type=feature_type, target_id=target_id)
        db.add(sched)
    sched.send_time = send_time
    sched.days_of_week = days_of_week
    sched.enabled = enabled
    await db.commit()
    await db.refresh(sched)
    return sched


async def delete_schedule(db: AsyncSession, feature_type: str, target_id: int) -> bool:
    sched = await get_schedule(db, feature_type, target_id)
    if sched is None:
        return False
    await db.delete(sched)
    await db.commit()
    return True


async def list_enabled(db: AsyncSession) -> list[Schedule]:
    res = await db.execute(select(Schedule).where(Schedule.enabled.is_(True)))
    return list(res.scalars().all())
```

- [ ] **Step 5: 테스트 실행(통과 확인)**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_schedule_store.py -q`
Expected: PASS (4 passed)

- [ ] **Step 6: 커밋**

```bash
git add app/services/scheduler/__init__.py app/services/scheduler/schedule_store.py tests/test_schedule_store.py
git commit -m "feat(2d): schedule_store CRUD"
```

---

## Task 3: 발송 로직 추출(chart_builder + chart_dispatch) + 라우트 축소

기존 `app/routers/charts.py`의 `_build_png`(시세→PNG)와 `send_telegram`(차트+AI 발송) 로직을
서비스 계층으로 추출해 수동/자동 발송이 공유하게 한다.

**Files:**
- Create: `app/services/chart/chart_builder.py`
- Create: `app/services/notification/chart_dispatch.py`
- Modify: `app/routers/charts.py`
- Test: `tests/test_charts_analyze.py` (send-telegram 테스트 patch 경로 갱신)

- [ ] **Step 1: chart_builder 작성**

Create `app/services/chart/chart_builder.py`:
```python
"""자산 → 차트 PNG. 라우터/디스패처가 공유(HTTPException 대신 도메인 예외)."""
import asyncio

from app.services.market.history_service import get_history
from app.services.chart.chart_service import generate_ta_chart, to_weekly

_DAYS = {"daily": 730, "weekly": 1825}


class ChartDataError(Exception):
    """차트용 시세 이력이 없거나 부족."""


async def build_png(asset, period: str) -> bytes:
    if period not in _DAYS:
        raise ChartDataError("period는 daily 또는 weekly")
    df = await get_history(asset, _DAYS[period])
    if df is None or len(df) < 20:
        raise ChartDataError("차트용 시세 이력을 가져올 수 없습니다(수동/이력없음 자산이거나 데이터 부족).")
    if period == "weekly":
        df = to_weekly(df)
        if len(df) < 20:
            raise ChartDataError("주봉 데이터가 부족합니다.")
    label = "WEEKLY" if period == "weekly" else "DAILY"
    return await asyncio.to_thread(generate_ta_chart, df, asset.ticker, asset.name, label)
```

- [ ] **Step 2: chart_dispatch 작성**

Create `app/services/notification/chart_dispatch.py`:
```python
"""차트 2장 + best-effort AI 분석 텔레그램 발송. 수동 라우트와 스케줄러가 공유."""
import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chart.chart_builder import build_png
from app.services.market.quote_service import get_quote
from app.services.notification import telegram_service
from app.services.ai import chart_analyzer

_log = logging.getLogger(__name__)


async def send_chart_telegram(db: AsyncSession, asset) -> dict:
    """일봉/주봉 발송 후 AI 분석을 best-effort로 발송. TelegramNotConfigured·ChartDataError는 전파."""
    quote = await get_quote(asset)
    caption = f"<b>{asset.name}</b> ({asset.ticker}·{asset.market})\n현재가: {quote.price:,} {asset.currency}"
    images: list[tuple[bytes, str]] = []
    sent = 0
    for i, period in enumerate(("daily", "weekly")):
        if i > 0:
            await asyncio.sleep(1)   # 텔레그램 연속 사진 rate limit 회피
        png = await build_png(asset, period)
        images.append((png, "image/png"))
        cap = f"{caption}\n[{period.upper()}]"
        if await telegram_service.send_photo(db, png, cap):
            sent += 1

    analysis_sent = False
    try:
        parts = await chart_analyzer.analyze(db, images, asset.ticker, asset.name, asset.market)
        for i, part in enumerate(parts):
            if i > 0:
                await asyncio.sleep(1)
            await telegram_service.send_message(db, part)
        analysis_sent = bool(parts)
    except (chart_analyzer.AnalysisDisabled, chart_analyzer.AnalysisNotConfigured):
        pass   # AI 미설정/비활성 → 차트만 발송
    except Exception as e:   # noqa: BLE001 — AI 실패가 차트 발송을 막지 않도록 best-effort
        _log.warning("AI 분석 발송 실패(차트는 발송됨): %s", e)

    return {"sent": sent, "ok": sent > 0, "analysis_sent": analysis_sent}
```

- [ ] **Step 3: charts.py 라우트 축소**

Modify `app/routers/charts.py`. imports 영역에서 history_service/chart_service/telegram_service/get_quote 직접 사용이 줄어든다. 다음과 같이 변경:

상단 import 블록을 다음으로 교체(기존 import 중 사용 안 하게 되는 것 정리):
```python
import io
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Asset
from app.services.chart.chart_builder import build_png, ChartDataError
from app.services.notification import telegram_service, chart_dispatch
from app.services.ai import chart_analyzer
from app.services.ai.llm_client import LiteLLMError

router = APIRouter(prefix="/api/charts", tags=["charts"])
```

`_build_png` 함수를 다음으로 교체(asset 조회 후 build_png 위임, 도메인 예외→HTTP):
```python
async def _build_png(db: AsyncSession, asset_id: int, period: str) -> bytes:
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    try:
        return await build_png(asset, period)
    except ChartDataError as e:
        raise HTTPException(422, str(e))
```

`send_telegram` 라우트를 다음으로 교체(chart_dispatch 위임):
```python
@router.post("/{asset_id}/send-telegram")
async def send_telegram(asset_id: int, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    try:
        return await chart_dispatch.send_chart_telegram(db, asset)
    except telegram_service.TelegramNotConfigured as e:
        raise HTTPException(409, str(e))
    except ChartDataError as e:
        raise HTTPException(422, str(e))
```

`chart`(GET)·`analyze`(POST) 라우트는 그대로 둔다(둘 다 `_build_png`를 통해 동작). 더 이상 쓰이지 않는 `import asyncio`, `from app.services.market.history_service import get_history`, `from app.services.chart.chart_service import generate_ta_chart, to_weekly`, `from app.services.market.quote_service import get_quote`, 모듈 상수 `_DAYS`는 삭제(위 import 블록 교체로 이미 빠짐 — `_DAYS`는 chart_builder로 이동했으므로 charts.py에서 제거).

- [ ] **Step 4: 기존 send-telegram 테스트 patch 경로 갱신**

Modify `tests/test_charts_analyze.py` — send-telegram 두 테스트가 이제 `chart_dispatch` 내부를 patch하도록 변경. 아래 두 함수를 교체:
```python
@pytest.mark.asyncio
async def test_send_telegram_best_effort_when_ai_disabled():
    quote = MagicMock(price=70000)
    with patch("app.services.notification.chart_dispatch.build_png", AsyncMock(return_value=b"\x89PNG")), \
         patch("app.services.notification.chart_dispatch.get_quote", AsyncMock(return_value=quote)), \
         patch("app.services.notification.chart_dispatch.telegram_service.send_photo", AsyncMock(return_value=True)), \
         patch("app.services.notification.chart_dispatch.chart_analyzer.analyze",
               AsyncMock(side_effect=chart_analyzer.AnalysisDisabled("off"))), \
         patch("app.db.AsyncSession.get", AsyncMock(return_value=_asset())):
        async with await _client() as ac:
            resp = await ac.post("/api/charts/1/send-telegram")
    body = resp.json()
    assert resp.status_code == 200
    assert body["sent"] == 2
    assert body["analysis_sent"] is False


@pytest.mark.asyncio
async def test_send_telegram_sends_analysis_when_enabled():
    quote = MagicMock(price=70000)
    with patch("app.services.notification.chart_dispatch.build_png", AsyncMock(return_value=b"\x89PNG")), \
         patch("app.services.notification.chart_dispatch.get_quote", AsyncMock(return_value=quote)), \
         patch("app.services.notification.chart_dispatch.telegram_service.send_photo", AsyncMock(return_value=True)), \
         patch("app.services.notification.chart_dispatch.telegram_service.send_message", AsyncMock(return_value=True)) as sm, \
         patch("app.services.notification.chart_dispatch.chart_analyzer.analyze",
               AsyncMock(return_value=["<b>분석</b>"])), \
         patch("app.db.AsyncSession.get", AsyncMock(return_value=_asset())):
        async with await _client() as ac:
            resp = await ac.post("/api/charts/1/send-telegram")
    assert resp.json()["analysis_sent"] is True
    sm.assert_awaited_once()
```

- [ ] **Step 5: 테스트 실행(통과 확인)**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_charts_analyze.py -q`
Expected: PASS (5 passed)

- [ ] **Step 6: 커밋**

```bash
git add app/services/chart/chart_builder.py app/services/notification/chart_dispatch.py app/routers/charts.py tests/test_charts_analyze.py
git commit -m "refactor(2d): extract chart_builder + chart_dispatch, slim charts routes"
```

---

## Task 4: 디스패처(_is_due + handlers + dispatch_tick)

**Files:**
- Create: `app/services/scheduler/handlers.py`
- Create: `app/services/scheduler/dispatcher.py`
- Test: `tests/test_scheduler_dispatcher.py`

- [ ] **Step 1: handlers 작성**

Create `app/services/scheduler/handlers.py`:
```python
"""feature_type별 발송 핸들러 + 레지스트리. 새 발송 기능은 여기 핸들러를 추가한다."""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, Schedule
from app.services.notification import chart_dispatch

_log = logging.getLogger(__name__)


async def handle_chart_analysis(db: AsyncSession, schedule: Schedule) -> None:
    asset = await db.get(Asset, schedule.target_id)
    if asset is None:
        _log.warning("스케줄 대상 asset 없음 target_id=%s", schedule.target_id)
        return
    await chart_dispatch.send_chart_telegram(db, asset)


HANDLERS = {"chart_analysis": handle_chart_analysis}
```

- [ ] **Step 2: 실패 테스트 작성**

Create `tests/test_scheduler_dispatcher.py`:
```python
import pytest
from datetime import datetime, date
from zoneinfo import ZoneInfo
from unittest.mock import patch, AsyncMock, MagicMock

from app.models import Schedule
from app.services.scheduler import dispatcher as d

_KST = ZoneInfo("Asia/Seoul")


def _sched(**kw):
    base = dict(feature_type="chart_analysis", target_id=1, send_time="08:00",
                days_of_week="0,1,2,3,4,5,6", enabled=True, last_run_date=None)
    base.update(kw)
    return Schedule(**base)


def test_is_due_true_when_time_passed_and_not_run():
    now = datetime(2026, 6, 16, 9, 0, tzinfo=_KST)  # 화요일(weekday=1), 08:00 지남
    assert d._is_due(_sched(), now) is True


def test_is_due_false_before_time():
    now = datetime(2026, 6, 16, 7, 30, tzinfo=_KST)
    assert d._is_due(_sched(), now) is False


def test_is_due_false_wrong_weekday():
    now = datetime(2026, 6, 16, 9, 0, tzinfo=_KST)  # 화(1)
    assert d._is_due(_sched(days_of_week="5,6"), now) is False


def test_is_due_false_already_ran_today():
    now = datetime(2026, 6, 16, 9, 0, tzinfo=_KST)
    assert d._is_due(_sched(last_run_date=date(2026, 6, 16)), now) is False


def test_is_due_false_when_disabled():
    now = datetime(2026, 6, 16, 9, 0, tzinfo=_KST)
    assert d._is_due(_sched(enabled=False), now) is False


@pytest.mark.asyncio
async def test_dispatch_tick_runs_due_and_sets_last_run():
    sched = _sched(send_time="00:00")   # 항상 시각 통과
    handler = AsyncMock()
    db = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=False)
    with patch.object(d, "SessionLocal", return_value=cm), \
         patch.object(d.schedule_store, "list_enabled", AsyncMock(return_value=[sched])), \
         patch.dict(d.HANDLERS, {"chart_analysis": handler}, clear=True):
        await d.dispatch_tick()
    handler.assert_awaited_once()
    assert sched.last_run_date is not None
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_dispatch_tick_failure_does_not_set_last_run():
    sched = _sched(send_time="00:00")
    handler = AsyncMock(side_effect=RuntimeError("boom"))
    db = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=False)
    with patch.object(d, "SessionLocal", return_value=cm), \
         patch.object(d.schedule_store, "list_enabled", AsyncMock(return_value=[sched])), \
         patch.dict(d.HANDLERS, {"chart_analysis": handler}, clear=True):
        await d.dispatch_tick()   # 예외가 tick 밖으로 새지 않아야 함
    assert sched.last_run_date is None
    db.rollback.assert_awaited()
```

- [ ] **Step 3: 테스트 실행(실패 확인)**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_scheduler_dispatcher.py -q`
Expected: FAIL (`cannot import name 'dispatcher'` / `_is_due` 없음)

- [ ] **Step 4: dispatcher 구현**

Create `app/services/scheduler/dispatcher.py`:
```python
"""1분 tick: due 스케줄을 순차 발송. _is_due는 순수 함수(테스트 대상)."""
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.db import SessionLocal
from app.models import Schedule
from app.services.scheduler import schedule_store
from app.services.scheduler.handlers import HANDLERS

_KST = ZoneInfo("Asia/Seoul")
_log = logging.getLogger(__name__)


def _parse_days(days_of_week: str) -> set[int]:
    out: set[int] = set()
    for tok in days_of_week.split(","):
        tok = tok.strip()
        if tok.isdigit():
            out.add(int(tok))
    return out


def _is_due(schedule: Schedule, now: datetime) -> bool:
    if not schedule.enabled:
        return False
    if now.weekday() not in _parse_days(schedule.days_of_week):
        return False
    hh, mm = schedule.send_time.split(":")
    if (now.hour, now.minute) < (int(hh), int(mm)):
        return False
    if schedule.last_run_date == now.date():
        return False
    return True


async def dispatch_tick() -> None:
    now = datetime.now(_KST)
    async with SessionLocal() as db:
        schedules = await schedule_store.list_enabled(db)
        due = [s for s in schedules if _is_due(s, now)]
        for i, sched in enumerate(due):
            if i > 0:
                await asyncio.sleep(2)   # 종목 간 발송 간격(텔레그램 rate limit 여유)
            handler = HANDLERS.get(sched.feature_type)
            if handler is None:
                _log.warning("미지의 feature_type=%s schedule_id=%s skip",
                             sched.feature_type, sched.schedule_id)
                continue
            try:
                await handler(db, sched)
                sched.last_run_date = now.date()
                await db.commit()
            except Exception as e:   # noqa: BLE001 — 한 건 실패가 나머지를 막지 않게
                await db.rollback()
                _log.warning("스케줄 발송 실패 schedule_id=%s: %s", sched.schedule_id, e)
```

- [ ] **Step 5: 테스트 실행(통과 확인)**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_scheduler_dispatcher.py -q`
Expected: PASS (7 passed)

- [ ] **Step 6: 커밋**

```bash
git add app/services/scheduler/handlers.py app/services/scheduler/dispatcher.py tests/test_scheduler_dispatcher.py
git commit -m "feat(2d): dispatcher (_is_due + dispatch_tick) + handler registry"
```

---

## Task 5: 스케줄러 래퍼 + lifespan 연결

**Files:**
- Create: `app/services/scheduler/scheduler.py`
- Modify: `app/main.py`

- [ ] **Step 1: scheduler 래퍼 작성**

Create `app/services/scheduler/scheduler.py`:
```python
"""AsyncIOScheduler 래퍼. tick 잡 1개만 등록(메모리 잡스토어, 진실의 원천은 schedules 테이블)."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.services.scheduler.dispatcher import dispatch_tick

_log = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None
_TICK_JOB_ID = "dispatch_tick"


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    _scheduler.add_job(dispatch_tick, "interval", minutes=1, id=_TICK_JOB_ID,
                       replace_existing=True, max_instances=1, coalesce=True)
    _scheduler.start()
    _log.info("스케줄러 시작(tick 1분 간격)")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
```

- [ ] **Step 2: lifespan에 연결**

Modify `app/main.py`. import 추가(`from app.bootstrap import ensure_schema` 아래):
```python
from app.services.scheduler.scheduler import start_scheduler, shutdown_scheduler
```
lifespan 함수를 다음으로 교체:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_schema(engine)   # 부팅 시 invest 스키마/테이블 멱등 생성
    start_scheduler()             # 1분 tick 디스패처 시작
    yield
    shutdown_scheduler()
    await engine.dispose()
```

- [ ] **Step 3: 스케줄러 import/구성 스모크 검증**

Run:
```bash
.venv/bin/python -c "from app.services.scheduler.scheduler import start_scheduler, shutdown_scheduler; print('ok')"
```
Expected: `ok` (import 에러 없음)

- [ ] **Step 4: 전체 테스트로 회귀 없음 확인**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q`
Expected: PASS (전체, 기존 + 신규)

- [ ] **Step 5: 커밋**

```bash
git add app/services/scheduler/scheduler.py app/main.py
git commit -m "feat(2d): AsyncIOScheduler wrapper + lifespan wiring"
```

---

## Task 6: 스케줄 CRUD API

**Files:**
- Modify: `app/routers/charts.py`
- Test: `tests/test_charts_schedule.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_charts_schedule.py`:
```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _asset():
    a = MagicMock()
    a.asset_id = 1
    return a


def _schedule_row():
    s = MagicMock()
    s.send_time = "08:30"
    s.days_of_week = "0,1,2,3,4"
    s.enabled = True
    return s


@pytest.mark.asyncio
async def test_get_schedule_null_when_absent():
    with patch("app.routers.charts.schedule_store.get_schedule", AsyncMock(return_value=None)):
        async with await _client() as ac:
            resp = await ac.get("/api/charts/1/schedule")
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.asyncio
async def test_get_schedule_returns_parsed():
    with patch("app.routers.charts.schedule_store.get_schedule", AsyncMock(return_value=_schedule_row())):
        async with await _client() as ac:
            resp = await ac.get("/api/charts/1/schedule")
    body = resp.json()
    assert body["send_time"] == "08:30"
    assert body["days_of_week"] == [0, 1, 2, 3, 4]
    assert body["enabled"] is True


@pytest.mark.asyncio
async def test_put_schedule_rejects_bad_time():
    async with await _client() as ac:
        resp = await ac.put("/api/charts/1/schedule",
                            json={"send_time": "25:00", "days_of_week": [0], "enabled": True})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_schedule_rejects_bad_day():
    async with await _client() as ac:
        resp = await ac.put("/api/charts/1/schedule",
                            json={"send_time": "08:00", "days_of_week": [7], "enabled": True})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_schedule_upserts():
    with patch("app.db.AsyncSession.get", AsyncMock(return_value=_asset())), \
         patch("app.routers.charts.schedule_store.upsert_schedule", AsyncMock()) as up:
        async with await _client() as ac:
            resp = await ac.put("/api/charts/1/schedule",
                                json={"send_time": "08:30", "days_of_week": [4, 0, 1], "enabled": True})
    assert resp.status_code == 200
    up.assert_awaited_once()
    # days는 정렬·중복제거된 콤마 문자열로 저장
    args = up.await_args.args
    assert args[4] == "0,1,4"


@pytest.mark.asyncio
async def test_put_schedule_404_when_asset_missing():
    with patch("app.db.AsyncSession.get", AsyncMock(return_value=None)):
        async with await _client() as ac:
            resp = await ac.put("/api/charts/1/schedule",
                                json={"send_time": "08:30", "days_of_week": [0], "enabled": True})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_schedule_ok():
    with patch("app.routers.charts.schedule_store.delete_schedule", AsyncMock(return_value=True)):
        async with await _client() as ac:
            resp = await ac.delete("/api/charts/1/schedule")
    assert resp.status_code == 200
```

- [ ] **Step 2: 테스트 실행(실패 확인)**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_charts_schedule.py -q`
Expected: FAIL (404 라우트 없음 / 422 대신 405 등)

- [ ] **Step 3: 스케줄 API 구현**

Modify `app/routers/charts.py`. 상단 import에 추가:
```python
import re
from pydantic import BaseModel, field_validator
from app.services.scheduler import schedule_store
from app.services.scheduler.schedule_store import FEATURE_CHART
```

파일 끝(마지막 라우트 뒤)에 추가:
```python
class ScheduleIn(BaseModel):
    send_time: str          # "HH:MM"
    days_of_week: list[int]  # 0(월)~6(일)
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


@router.get("/{asset_id}/schedule")
async def get_schedule(asset_id: int, db: AsyncSession = Depends(get_db)):
    sched = await schedule_store.get_schedule(db, FEATURE_CHART, asset_id)
    if sched is None:
        return None
    return {
        "send_time": sched.send_time,
        "days_of_week": [int(x) for x in sched.days_of_week.split(",") if x != ""],
        "enabled": sched.enabled,
    }


@router.put("/{asset_id}/schedule")
async def put_schedule(asset_id: int, body: ScheduleIn, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    days = ",".join(str(d) for d in sorted(set(body.days_of_week)))
    await schedule_store.upsert_schedule(db, FEATURE_CHART, asset_id, body.send_time, days, body.enabled)
    return {"status": "ok"}


@router.delete("/{asset_id}/schedule")
async def delete_schedule(asset_id: int, db: AsyncSession = Depends(get_db)):
    await schedule_store.delete_schedule(db, FEATURE_CHART, asset_id)
    return {"status": "ok"}
```

주: `/{asset_id}/schedule`은 `/{asset_id}`(GET, 세그먼트 1개)와 경로 세그먼트 수가 달라 충돌하지 않는다.

- [ ] **Step 4: 테스트 실행(통과 확인)**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_charts_schedule.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: 커밋**

```bash
git add app/routers/charts.py tests/test_charts_schedule.py
git commit -m "feat(2d): schedule CRUD API (GET/PUT/DELETE /api/charts/{id}/schedule)"
```

---

## Task 7: 프론트엔드(api.ts + Charts.tsx 스케줄 섹션)

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/pages/Charts.tsx`

- [ ] **Step 1: api.ts에 스케줄 함수 추가**

Modify `frontend/src/api.ts` — `analyzeChart` 항목 근처에 추가:
```typescript
  getSchedule: (id: number) =>
    j<{ send_time: string; days_of_week: number[]; enabled: boolean } | null>(`/api/charts/${id}/schedule`),
  saveSchedule: (id: number, s: { send_time: string; days_of_week: number[]; enabled: boolean }) =>
    j(`/api/charts/${id}/schedule`, { method: "PUT", body: JSON.stringify(s) }),
  deleteSchedule: (id: number) =>
    j(`/api/charts/${id}/schedule`, { method: "DELETE" }),
```
(파일의 기존 객체 구문/콤마 스타일에 맞춰 삽입한다.)

- [ ] **Step 2: Charts.tsx에 스케줄 상태 + 로딩 추가**

Modify `frontend/src/pages/Charts.tsx`. 컴포넌트 상태 선언부(`const [analyzing, ...]` 아래)에 추가:
```typescript
  const [schedTime, setSchedTime] = useState("08:30");
  const [schedDays, setSchedDays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [schedEnabled, setSchedEnabled] = useState(false);
  const [schedMsg, setSchedMsg] = useState("");
```

종목 선택 시 스케줄을 로드하도록, 기존 첫 `useEffect`(listAssets) 아래에 추가:
```typescript
  useEffect(() => {
    if (!assetId) return;
    api.getSchedule(assetId).then((s) => {
      if (s) { setSchedTime(s.send_time); setSchedDays(s.days_of_week); setSchedEnabled(s.enabled); }
      else { setSchedTime("08:30"); setSchedDays([0, 1, 2, 3, 4]); setSchedEnabled(false); }
      setSchedMsg("");
    });
  }, [assetId]);
```

저장/삭제 핸들러를 `analyze` 함수 아래에 추가:
```typescript
  const DAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"];
  const toggleDay = (d: number) =>
    setSchedDays((prev) => prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort());

  const saveSched = async () => {
    if (!assetId) return;
    setSchedMsg("저장 중…");
    try {
      await api.saveSchedule(assetId, { send_time: schedTime, days_of_week: schedDays, enabled: schedEnabled });
      setSchedMsg("저장됨");
    } catch (e: any) { setSchedMsg("저장 실패: " + e.message); }
  };

  const deleteSched = async () => {
    if (!assetId) return;
    setSchedMsg("삭제 중…");
    try {
      await api.deleteSchedule(assetId);
      setSchedEnabled(false); setSchedMsg("삭제됨");
    } catch (e: any) { setSchedMsg("삭제 실패: " + e.message); }
  };
```

- [ ] **Step 3: Charts.tsx에 스케줄 UI 섹션 추가**

`analysis` 패널(`{analysis && (...)}`) 블록 바로 아래에 추가:
```tsx
      {assetId && (
        <div className="border rounded p-3 bg-white max-w-3xl space-y-2">
          <h2 className="font-semibold text-gray-700">자동 발송 스케줄</h2>
          <div className="flex items-center gap-2 flex-wrap">
            <label className="text-sm">발송 시각</label>
            <input type="time" className="border rounded px-2 py-1"
              value={schedTime} onChange={(e) => setSchedTime(e.target.value)} />
            <span className="text-xs text-gray-500">(KST)</span>
          </div>
          <div className="flex items-center gap-1 flex-wrap">
            {DAY_LABELS.map((lbl, d) => (
              <button key={d} type="button" onClick={() => toggleDay(d)}
                className={`px-2 py-1 rounded text-sm border ${schedDays.includes(d) ? "bg-blue-600 text-white" : "bg-gray-100"}`}>
                {lbl}
              </button>
            ))}
          </div>
          <label className="flex gap-2 items-center text-sm">
            <input type="checkbox" checked={schedEnabled} onChange={(e) => setSchedEnabled(e.target.checked)} />
            스케줄 활성화
          </label>
          <div className="flex gap-2 items-center">
            <button onClick={saveSched} className="px-3 py-1 rounded bg-blue-600 text-white">저장</button>
            <button onClick={deleteSched} className="px-3 py-1 rounded bg-gray-500 text-white">삭제</button>
            {schedMsg && <span className="text-sm text-gray-600">{schedMsg}</span>}
          </div>
        </div>
      )}
```

- [ ] **Step 4: 빌드 검증**

Run: `cd frontend && npm run build`
Expected: 빌드 성공(타입 에러 없음), `app/static/ui`에 산출물 생성.

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/api.ts frontend/src/pages/Charts.tsx frontend/src/static 2>/dev/null; git add frontend/
git commit -m "feat(2d): chart auto-send schedule UI"
```

---

## Task 8: 전체 검증 + ROADMAP 갱신

**Files:**
- Modify: `docs/superpowers/ROADMAP.md`

- [ ] **Step 1: 전체 테스트 실행**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q`
Expected: 전체 PASS(기존 68 + 신규: schedule_store 4 + dispatcher 7 + charts_schedule 7 + table 1 = 87 내외).

- [ ] **Step 2: 프론트 빌드 재확인**

Run: `cd frontend && npm run build`
Expected: 성공.

- [ ] **Step 3: ROADMAP 2d 섹션 갱신**

Modify `docs/superpowers/ROADMAP.md` — `### 2d: 스케줄 자동 발송 — **미착수**` 섹션을 다음으로 교체:
```markdown
### 2d: 스케줄 자동 발송 — **구현 완료 (2026-06-16)**
- spec: `docs/superpowers/specs/2026-06-16-scheduled-auto-send-design.md`
- plan: `docs/superpowers/plans/2026-06-16-scheduled-auto-send.md`
- 내용: 신규 `schedules` 테이블(범용: feature_type/target_id/send_time/days_of_week/enabled/last_run_date, ensure_schema 자동생성) + `app/services/scheduler/`(AsyncIOScheduler 메모리 잡스토어 + 1분 tick 디스패처 + `_is_due` 순수함수 + feature_type 핸들러 레지스트리). 발송 로직은 `chart_dispatch.send_chart_telegram`(라우트에서 추출)·`chart_builder.build_png`로 분리해 수동 발송/자동 발송이 공유. 스케줄 CRUD API(GET/PUT/DELETE `/api/charts/{id}/schedule`), main.py lifespan에 start/shutdown_scheduler. 프론트: 차트 페이지 "자동 발송 스케줄" 섹션(시각/요일/활성화).
- 결정: 종목당 1개 스케줄, 잡스토어=메모리(진실의 원천=DB 테이블), KST 고정, 미스된 실행은 그날 안 늦게라도 발송(자정 넘기면 폐기), 방해금지 로직 없음. 중앙 디스패처라 여러 발송 기능이 같은 테이블·tick을 공유(향후 확장점).
- 상태: 단위/통합테스트 통과, 프론트 빌드 통과. **실 스케줄 스모크는 사용자 확인 필요(가까운 시각 등록 후 발송 확인).**
- 비고: 종목당 복수 스케줄·PG 잡스토어·기능별 별도 테이블·자정 catch-up·발송 이력 로그는 YAGNI로 제외.
```

- [ ] **Step 4: 커밋**

```bash
git add docs/superpowers/ROADMAP.md
git commit -m "docs(2d): mark scheduled auto-send complete"
```

---

## Self-Review 결과

- **Spec 커버리지:** schedules 테이블(T1) / schedule_store(T2) / 발송 로직 추출·재사용(T3) / 디스패처·_is_due·핸들러(T4) / 스케줄러·lifespan(T5) / CRUD API(T6) / 프론트(T7) / 검증·ROADMAP(T8) — spec 전 항목 매핑됨.
- **Placeholder:** 없음(모든 코드·명령·기대출력 명시).
- **타입/시그니처 일관성:** `send_chart_telegram(db, asset)`, `build_png(asset, period)`, `_is_due(schedule, now)`, `dispatch_tick()`, `HANDLERS`, `schedule_store.{get,upsert,delete,list_enabled}` — 태스크 간 호출 시그니처 일치 확인. `upsert_schedule(db, feature_type, target_id, send_time, days_of_week, enabled)` 인자 순서가 T6 테스트의 `args[4]==days`와 일치(0:db,1:feature,2:target,3:send_time,4:days,5:enabled).
