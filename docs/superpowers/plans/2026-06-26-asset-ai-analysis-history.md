# 종목별 AI 분석 — 마크다운 렌더링 + 히스토리 저장 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목 차트 AI 분석을 마크다운으로 정규화해 웹에서 올바로 렌더하고, 종목당 최신 20건을 자동 저장·조회하는 히스토리 기능을 추가한다.

**Architecture:** LLM이 텔레그램 HTML 대신 마크다운을 출력하도록 프롬프트를 바꾸고(`analyze_raw`는 `(text, model)` 반환), 텔레그램은 기존 `md_to_telegram_html` 변환기를 재사용한다. 신규 `asset_ai_analyses` 테이블과 `analysis_store`(N건 prune)를 두고, 웹 분석 엔드포인트와 텔레그램 디스패치가 분석 실행 시 자동 저장한다. 프론트는 `react-markdown`으로 최신 분석을 렌더하고 과거 분석을 접이식 히스토리로 보여준다.

**Tech Stack:** FastAPI · async SQLAlchemy 2.0 · asyncpg · PostgreSQL(`invest` 스키마) · pytest-asyncio · React 19 + Vite + TS + Tailwind · react-markdown

**설계 spec:** `docs/superpowers/specs/2026-06-26-asset-ai-analysis-history-design.md`

---

## 파일 구조

**백엔드 — 생성**
- `app/models/asset_ai_analysis.py` — `AssetAIAnalysis` ORM 모델
- `app/services/ai/analysis_store.py` — 저장/조회/prune CRUD
- `tests/test_analysis_store.py` — store DB 통합 테스트
- `tests/test_charts_analyses_api.py` — GET 목록 / DELETE 엔드포인트 테스트

**백엔드 — 수정**
- `app/models/__init__.py` — 신규 모델 export
- `app/services/ai/chart_analyzer.py` — 마크다운 출력 instruction, `analyze_raw` → `(text, model)`
- `app/services/notification/chart_dispatch.py` — 마크다운 1회 생성 → 저장 → 텔레그램 변환, `trigger` 파라미터
- `app/services/scheduler/handlers.py` — `send_chart_telegram(..., trigger="scheduled")`
- `app/routers/charts.py` — analyze 저장, GET `/analyses`, DELETE
- `tests/test_chart_analyzer.py` — 프롬프트·튜플 반환 변경 반영
- `tests/test_charts_analyze.py` — analyze 저장·send-telegram 리팩터 반영

**프론트 — 수정**
- `frontend/package.json` — `react-markdown` 의존성
- `frontend/src/api.ts` — `AssetAnalysis` 타입 + `listAnalyses`/`deleteAnalysis`, `analyzeChart` 응답 확장
- `frontend/src/pages/AssetDetail.tsx` — 마크다운 렌더 + 히스토리 UI

---

## Task 1: AssetAIAnalysis 모델 + analysis_store

**Files:**
- Create: `app/models/asset_ai_analysis.py`
- Modify: `app/models/__init__.py`
- Create: `app/services/ai/analysis_store.py`
- Test: `tests/test_analysis_store.py`

- [ ] **Step 1: 모델 작성**

Create `app/models/asset_ai_analysis.py` (`ai_report.py` 스타일 + `asset_id` FK/인덱스. Asset PK 컬럼명은 `asset_id`이므로 FK는 `assets.asset_id`):

```python
from datetime import datetime
from sqlalchemy import Text, String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class AssetAIAnalysis(Base):
    __tablename__ = "asset_ai_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.asset_id", ondelete="CASCADE"), index=True, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False, default="")
    trigger: Mapped[str] = mapped_column(String, nullable=False, default="manual")  # manual | scheduled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: 모델 export 등록**

Modify `app/models/__init__.py` — import 줄과 `__all__`에 추가:

```python
from app.models.journal_entry import JournalEntry
from app.models.asset_ai_analysis import AssetAIAnalysis

__all__ = ["Asset", "ExchangeRate", "PriceSnapshot", "Holding", "AppSetting",
           "CashBalance", "Schedule", "PriceAlert", "PortfolioSnapshot", "AIReport",
           "JournalEntry", "AssetAIAnalysis"]
```

- [ ] **Step 3: store 실패 테스트 작성**

Create `tests/test_analysis_store.py` (`test_report_store.py`의 `db_session` 통합 패턴):

```python
import pytest
from sqlalchemy import select
from app.models.asset_ai_analysis import AssetAIAnalysis
from app.models.asset import Asset
from app.services.ai import analysis_store


async def _make_asset(db, ticker="005930"):
    a = Asset(ticker=ticker, name="삼성전자", asset_type="stock", market="KR",
              currency="KRW", data_source="pykrx", fetch_symbol=ticker)
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


@pytest.mark.asyncio
async def test_table_created(db_session):
    rows = (await db_session.execute(select(AssetAIAnalysis))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_create_and_list_newest_first(db_session):
    a = await _make_asset(db_session)
    r1 = await analysis_store.create_and_prune(db_session, a.asset_id, "## A", "m", "manual")
    r2 = await analysis_store.create_and_prune(db_session, a.asset_id, "## B", "m", "scheduled")
    rows = await analysis_store.list_for_asset(db_session, a.asset_id)
    assert [r.id for r in rows] == [r2.id, r1.id]
    assert rows[0].content_md == "## B"


@pytest.mark.asyncio
async def test_prune_keeps_only_n(db_session):
    a = await _make_asset(db_session)
    for i in range(23):
        await analysis_store.create_and_prune(db_session, a.asset_id, f"#{i}", "m", "manual", keep=20)
    rows = await analysis_store.list_for_asset(db_session, a.asset_id, limit=100)
    assert len(rows) == 20
    assert rows[0].content_md == "#22"   # 최신 유지
    assert all(r.content_md != "#0" for r in rows)  # 가장 오래된 것 삭제됨


@pytest.mark.asyncio
async def test_prune_isolated_per_asset(db_session):
    a = await _make_asset(db_session, "005930")
    b = await _make_asset(db_session, "000660")
    for i in range(22):
        await analysis_store.create_and_prune(db_session, a.asset_id, f"a{i}", "m", "manual", keep=20)
    await analysis_store.create_and_prune(db_session, b.asset_id, "b0", "m", "manual", keep=20)
    assert len(await analysis_store.list_for_asset(db_session, a.asset_id, limit=100)) == 20
    assert len(await analysis_store.list_for_asset(db_session, b.asset_id, limit=100)) == 1


@pytest.mark.asyncio
async def test_delete(db_session):
    a = await _make_asset(db_session)
    r = await analysis_store.create_and_prune(db_session, a.asset_id, "x", "m", "manual")
    assert await analysis_store.delete(db_session, r.id) is True
    assert await analysis_store.delete(db_session, 999999) is False
```

- [ ] **Step 4: 테스트 실패 확인**

Run: `python -m pytest tests/test_analysis_store.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.ai.analysis_store` (또는 import 에러)

- [ ] **Step 5: store 구현**

Create `app/services/ai/analysis_store.py`:

```python
"""asset_ai_analyses 테이블 CRUD. 종목당 최신 KEEP건만 유지."""
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_ai_analysis import AssetAIAnalysis

KEEP_DEFAULT = 20


async def create_and_prune(db: AsyncSession, asset_id: int, content_md: str,
                           model: str, trigger: str,
                           keep: int = KEEP_DEFAULT) -> AssetAIAnalysis:
    row = AssetAIAnalysis(asset_id=asset_id, content_md=content_md,
                          model=model, trigger=trigger)
    db.add(row)
    await db.commit()
    await db.refresh(row)

    # 같은 종목에서 최신 keep건만 남기고 나머지 삭제(id 내림차순 = 최신순).
    keep_ids = (await db.execute(
        select(AssetAIAnalysis.id)
        .where(AssetAIAnalysis.asset_id == asset_id)
        .order_by(AssetAIAnalysis.id.desc())
        .limit(keep)
    )).scalars().all()
    await db.execute(
        sa_delete(AssetAIAnalysis)
        .where(AssetAIAnalysis.asset_id == asset_id)
        .where(AssetAIAnalysis.id.notin_(keep_ids))
    )
    await db.commit()
    return row


async def list_for_asset(db: AsyncSession, asset_id: int,
                         limit: int = KEEP_DEFAULT) -> list[AssetAIAnalysis]:
    res = await db.execute(
        select(AssetAIAnalysis)
        .where(AssetAIAnalysis.asset_id == asset_id)
        .order_by(AssetAIAnalysis.id.desc())
        .limit(limit)
    )
    return list(res.scalars().all())


async def delete(db: AsyncSession, analysis_id: int) -> bool:
    row = await db.get(AssetAIAnalysis, analysis_id)
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `python -m pytest tests/test_analysis_store.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: 커밋**

```bash
git add app/models/asset_ai_analysis.py app/models/__init__.py app/services/ai/analysis_store.py tests/test_analysis_store.py
git commit -m "feat(ai): asset_ai_analyses 모델 + 종목당 N건 보관 analysis_store"
```

---

## Task 2: chart_analyzer 마크다운 출력 + analyze_raw (text, model) 반환

**Files:**
- Modify: `app/services/ai/chart_analyzer.py`
- Test: `tests/test_chart_analyzer.py`

배경: 현재 `_TELEGRAM_FORMAT_INSTRUCTION`이 LLM에게 HTML 태그를 강제해 웹에서 태그가 노출된다. 마크다운 출력으로 바꾸고, 저장에 쓸 모델명을 함께 반환한다.

- [ ] **Step 1: 기존 테스트를 새 동작에 맞게 수정(실패 유도)**

Modify `tests/test_chart_analyzer.py`:

`test_build_prompt_prepends_meta_and_appends_format`의 마지막 줄을 교체 — 프롬프트에 더는 HTML 태그가 없고 마크다운 지시가 들어간다:

```python
def test_build_prompt_prepends_meta_and_appends_format():
    p = ca._build_prompt("USER", "AAPL", "Apple", "US", ["일봉 (1년)", "주봉 (5년)"])
    assert "AAPL" in p and "Apple" in p and "US" in p
    assert "USER" in p
    assert "<b>" not in p and "<i>" not in p   # HTML 태그 강제 제거
    assert "마크다운" in p                       # 마크다운 출력 지시 포함
```

`test_analyze_raw_returns_unconverted_markdown`을 튜플 반환에 맞게 교체:

```python
@pytest.mark.asyncio
async def test_analyze_raw_returns_markdown_and_model():
    db = MagicMock()
    cfg = {"base_url": "http://gw", "api_key": "K", "model": "m", "prompt": "P"}
    with patch.object(ca, "load_config", AsyncMock(return_value=cfg)), \
         patch.object(ca.llm_client, "analyze_images",
                      AsyncMock(return_value="**요약**")):
        text, model = await ca.analyze_raw(db, [(b"d", "image/png"), (b"w", "image/png")],
                                           "AAPL", "Apple", "US")
    assert text == "**요약**"
    assert model == "m"
    assert "<b>" not in text
```

(`test_analyze_calls_client_and_formats`는 그대로 두되 `analyze`가 내부에서 튜플을 unpack하므로 결과 `parts == ["<b>요약</b>"]` 유지된다.)

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_chart_analyzer.py -v`
Expected: FAIL — `test_build_prompt...`(여전히 `<b>` 포함), `test_analyze_raw...`(str엔 unpack 불가 / 또는 ValueError)

- [ ] **Step 3: 마크다운 instruction으로 교체**

Modify `app/services/ai/chart_analyzer.py` — `_TELEGRAM_FORMAT_INSTRUCTION` 상수를 다음으로 교체(이름도 변경):

```python
_FORMAT_INSTRUCTION = """

[출력 형식]
- 마크다운으로 작성합니다. 일반 텍스트/HTML 태그를 직접 쓰지 마세요.
- 섹션 헤더는 `## 섹션명`, 강조는 `**굵게**`, 약한 강조는 `*기울임*`, 코드/수치는 `` `값` ``.
- 항목은 `- ` 불릿으로, 개조식으로 작성합니다.
- 전체 분량: 한글 1,500~2,500자 권장"""
```

- [ ] **Step 4: `_build_prompt`에서 새 상수 사용**

Modify `chart_analyzer.py` `_build_prompt` 마지막 줄:

```python
    return meta + user_prompt + _FORMAT_INSTRUCTION
```

- [ ] **Step 5: `analyze_raw`가 (text, model) 반환하도록 변경**

Modify `chart_analyzer.py` `analyze_raw`:

```python
async def analyze_raw(db: AsyncSession, images: list[tuple[bytes, str]],
                      ticker: str, name: str, market: str) -> tuple[str, str]:
    """이미지(일봉,주봉 순) → (LLM 마크다운 원문, 모델명). 미설정/비활성/실패는 예외 전파."""
    cfg = await load_config(db)
    chart_labels = ["일봉 (1년)", "주봉 (5년)"][:len(images)]
    prompt = _build_prompt(cfg["prompt"], ticker, name, market, chart_labels)
    text = await llm_client.analyze_images(
        base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"],
        images=images, prompt=prompt,
        temperature=_TEMPERATURE, max_output_tokens=_MAX_OUTPUT_TOKENS)
    return text, cfg["model"]
```

- [ ] **Step 6: `analyze`가 튜플을 unpack하도록 변경**

Modify `chart_analyzer.py` `analyze`:

```python
async def analyze(db: AsyncSession, images: list[tuple[bytes, str]],
                  ticker: str, name: str, market: str) -> list[str]:
    """이미지(일봉,주봉 순) → 텔레그램 HTML 메시지 조각 리스트. 미설정/비활성/실패는 예외 전파."""
    raw, _model = await analyze_raw(db, images, ticker, name, market)
    return telegram_md.split_message(telegram_md.md_to_telegram_html(raw))
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `python -m pytest tests/test_chart_analyzer.py -v`
Expected: PASS (모든 테스트)

- [ ] **Step 8: 커밋**

```bash
git add app/services/ai/chart_analyzer.py tests/test_chart_analyzer.py
git commit -m "refactor(ai): chart_analyzer 출력을 마크다운으로 정규화 + analyze_raw가 모델명 동반 반환"
```

---

## Task 3: chart_dispatch 리팩터 — 마크다운 저장 + 텔레그램 변환

**Files:**
- Modify: `app/services/notification/chart_dispatch.py`
- Modify: `app/services/scheduler/handlers.py`
- Test: `tests/test_charts_analyze.py` (send-telegram 테스트)

배경: 디스패치가 `chart_analyzer.analyze`(텔레그램 HTML)를 호출하던 것을 `analyze_raw`(마크다운) 1회 호출로 바꿔, 저장과 텔레그램 발송을 한 소스에서 처리한다.

- [ ] **Step 1: send-telegram 테스트를 새 구조에 맞게 수정(실패 유도)**

Modify `tests/test_charts_analyze.py` — `_asset()` 헬퍼에 `asset_id` 추가:

```python
def _asset():
    a = MagicMock()
    a.asset_id = 1
    a.ticker, a.name, a.market, a.currency = "005930", "삼성전자", "KR", "KRW"
    return a
```

`test_send_telegram_best_effort_when_ai_disabled` 교체 — `analyze` 대신 `analyze_raw`를 patch(AnalysisDisabled), store는 호출되지 않음:

```python
@pytest.mark.asyncio
async def test_send_telegram_best_effort_when_ai_disabled():
    quote = MagicMock(price=70000)
    with patch("app.services.notification.chart_dispatch.build_png", AsyncMock(return_value=b"\x89PNG")), \
         patch("app.services.notification.chart_dispatch.get_quote", AsyncMock(return_value=quote)), \
         patch("app.services.notification.chart_dispatch.telegram_service.send_photo", AsyncMock(return_value=True)), \
         patch("app.services.notification.chart_dispatch.chart_analyzer.analyze_raw",
               AsyncMock(side_effect=chart_analyzer.AnalysisDisabled("off"))), \
         patch("app.services.notification.chart_dispatch.analysis_store.create_and_prune",
               AsyncMock()) as store, \
         patch("app.db.AsyncSession.get", AsyncMock(return_value=_asset())):
        async with await _client() as ac:
            resp = await ac.post("/api/charts/1/send-telegram")
    body = resp.json()
    assert resp.status_code == 200
    assert body["sent"] == 2
    assert body["analysis_sent"] is False
    store.assert_not_awaited()   # 분석 비활성 시 저장 안 함
```

`test_send_telegram_sends_analysis_when_enabled` 교체 — `analyze_raw`가 (md, model) 반환, store 호출, 텔레그램으로 변환 발송:

```python
@pytest.mark.asyncio
async def test_send_telegram_sends_analysis_when_enabled():
    quote = MagicMock(price=70000)
    with patch("app.services.notification.chart_dispatch.build_png", AsyncMock(return_value=b"\x89PNG")), \
         patch("app.services.notification.chart_dispatch.get_quote", AsyncMock(return_value=quote)), \
         patch("app.services.notification.chart_dispatch.telegram_service.send_photo", AsyncMock(return_value=True)), \
         patch("app.services.notification.chart_dispatch.telegram_service.send_message", AsyncMock(return_value=True)) as sm, \
         patch("app.services.notification.chart_dispatch.chart_analyzer.analyze_raw",
               AsyncMock(return_value=("**분석**", "gemini/x"))), \
         patch("app.services.notification.chart_dispatch.analysis_store.create_and_prune",
               AsyncMock()) as store, \
         patch("app.db.AsyncSession.get", AsyncMock(return_value=_asset())):
        async with await _client() as ac:
            resp = await ac.post("/api/charts/1/send-telegram")
    assert resp.json()["analysis_sent"] is True
    sm.assert_awaited()                       # 변환된 메시지 발송
    store.assert_awaited_once()               # 마크다운 저장
    _args, kwargs = store.await_args
    assert kwargs.get("trigger", "manual") == "manual"  # 수동 발송
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_charts_analyze.py -k send_telegram -v`
Expected: FAIL — 현재 dispatch는 `analyze_raw`/`analysis_store`를 쓰지 않음(patch 대상 부재 또는 store 미호출)

- [ ] **Step 3: chart_dispatch 리팩터**

Modify `app/services/notification/chart_dispatch.py` — import에 추가:

```python
from app.services.ai import chart_analyzer
from app.services.ai import telegram_md
from app.services.ai import analysis_store
```

`send_chart_telegram` 시그니처와 분석 블록 교체:

```python
async def send_chart_telegram(db: AsyncSession, asset, trigger: str = "manual") -> dict:
    """일봉/주봉 발송 후 AI 분석을 best-effort로 저장·발송. TelegramNotConfigured·ChartDataError는 전파."""
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
        raw, model = await chart_analyzer.analyze_raw(db, images, asset.ticker, asset.name, asset.market)
        try:
            await analysis_store.create_and_prune(db, asset.asset_id, raw, model, trigger=trigger)
        except Exception as e:   # noqa: BLE001 — 저장 실패가 발송을 막지 않도록
            _log.warning("AI 분석 저장 실패(발송은 진행): %s", e)
        parts = telegram_md.split_message(telegram_md.md_to_telegram_html(raw))
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

- [ ] **Step 4: 스케줄러 핸들러에 trigger 전달**

Modify `app/services/scheduler/handlers.py:27` — `send_chart_telegram(db, asset)` 호출을 다음으로:

```python
    await chart_dispatch.send_chart_telegram(db, asset, trigger="scheduled")
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_charts_analyze.py -k send_telegram -v`
Expected: PASS (2 tests)

- [ ] **Step 6: 커밋**

```bash
git add app/services/notification/chart_dispatch.py app/services/scheduler/handlers.py tests/test_charts_analyze.py
git commit -m "refactor(notify): chart_dispatch가 마크다운 분석을 저장 후 텔레그램 변환 발송(trigger 구분)"
```

---

## Task 4: charts API — analyze 자동 저장 + 히스토리 GET/DELETE

**Files:**
- Modify: `app/routers/charts.py`
- Test: `tests/test_charts_analyze.py` (analyze 저장), `tests/test_charts_analyses_api.py` (GET/DELETE)

- [ ] **Step 1: analyze 저장 테스트 수정(실패 유도)**

Modify `tests/test_charts_analyze.py` `test_analyze_returns_text` — `analyze_raw`는 튜플 반환, store를 patch, 응답에 id/created_at 포함:

```python
@pytest.mark.asyncio
async def test_analyze_returns_text_and_saves():
    from datetime import datetime, timezone
    row = MagicMock(id=7, created_at=datetime(2026, 6, 26, tzinfo=timezone.utc))
    with patch("app.routers.charts._build_png", AsyncMock(return_value=b"\x89PNG")), \
         patch("app.routers.charts.chart_analyzer.analyze_raw",
               AsyncMock(return_value=("**요약**\n\n두번째", "gemini/x"))), \
         patch("app.routers.charts.analysis_store.create_and_prune",
               AsyncMock(return_value=row)) as store, \
         patch("app.db.AsyncSession.get", AsyncMock(return_value=_asset())):
        async with await _client() as ac:
            resp = await ac.post("/api/charts/1/analyze")
    assert resp.status_code == 200
    body = resp.json()
    assert body["analysis"] == "**요약**\n\n두번째"
    assert body["id"] == 7
    store.assert_awaited_once()
    _args, kwargs = store.await_args
    assert kwargs.get("trigger", "manual") == "manual"
```

`test_analyze_disabled_returns_409`, `test_analyze_gateway_error_returns_502`는 `analyze_raw`가 예외를 던지므로 저장 patch 없이 그대로 통과한다(수정 불필요).

- [ ] **Step 2: GET/DELETE 테스트 작성(실패 유도)**

Create `tests/test_charts_analyses_api.py`:

```python
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_list_analyses():
    rows = [
        MagicMock(id=2, asset_id=1, content_md="## B", model="m", trigger="manual",
                  created_at=datetime(2026, 6, 26, 9, tzinfo=timezone.utc)),
        MagicMock(id=1, asset_id=1, content_md="## A", model="m", trigger="scheduled",
                  created_at=datetime(2026, 6, 25, 9, tzinfo=timezone.utc)),
    ]
    with patch("app.routers.charts.analysis_store.list_for_asset",
               AsyncMock(return_value=rows)):
        async with await _client() as ac:
            resp = await ac.get("/api/charts/1/analyses")
    assert resp.status_code == 200
    body = resp.json()
    assert [r["id"] for r in body] == [2, 1]
    assert body[0]["content_md"] == "## B"
    assert body[0]["trigger"] == "manual"


@pytest.mark.asyncio
async def test_delete_analysis_found():
    with patch("app.routers.charts.analysis_store.delete", AsyncMock(return_value=True)):
        async with await _client() as ac:
            resp = await ac.delete("/api/charts/analyses/5")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_delete_analysis_missing_404():
    with patch("app.routers.charts.analysis_store.delete", AsyncMock(return_value=False)):
        async with await _client() as ac:
            resp = await ac.delete("/api/charts/analyses/999")
    assert resp.status_code == 404
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python -m pytest tests/test_charts_analyses_api.py tests/test_charts_analyze.py -k "analyses or saves" -v`
Expected: FAIL — `analysis_store` 미import / `/analyses` 라우트 부재(404 또는 422)

- [ ] **Step 4: charts.py 수정 — import + analyze 저장**

Modify `app/routers/charts.py` — import 추가:

```python
from app.services.ai import analysis_store
```

`analyze` 엔드포인트 본문 교체:

```python
@router.post("/{asset_id}/analyze")
async def analyze(asset_id: int, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    images = [(await _build_png(db, asset_id, p), "image/png") for p in ("daily", "weekly")]
    try:
        text, model = await chart_analyzer.analyze_raw(db, images, asset.ticker, asset.name, asset.market)
    except (chart_analyzer.AnalysisDisabled, chart_analyzer.AnalysisNotConfigured) as e:
        raise HTTPException(409, str(e))
    except LiteLLMError as e:
        raise HTTPException(502, str(e))
    row = await analysis_store.create_and_prune(db, asset_id, text, model, trigger="manual")
    return {"analysis": text, "id": row.id, "created_at": row.created_at}
```

- [ ] **Step 5: charts.py 수정 — GET 목록 + DELETE**

Modify `app/routers/charts.py` — analyze 엔드포인트 바로 아래에 추가:

```python
@router.get("/{asset_id}/analyses")
async def list_analyses(asset_id: int, limit: int = Query(20, ge=1, le=100),
                        db: AsyncSession = Depends(get_db)):
    rows = await analysis_store.list_for_asset(db, asset_id, limit=limit)
    return [
        {"id": r.id, "asset_id": r.asset_id, "content_md": r.content_md,
         "model": r.model, "trigger": r.trigger, "created_at": r.created_at}
        for r in rows
    ]


@router.delete("/analyses/{analysis_id}")
async def delete_analysis(analysis_id: int, db: AsyncSession = Depends(get_db)):
    if not await analysis_store.delete(db, analysis_id):
        raise HTTPException(404, "analysis not found")
    return {"ok": True}
```

(`Query`는 파일 상단에서 이미 import됨.)

- [ ] **Step 6: 테스트 통과 확인**

Run: `python -m pytest tests/test_charts_analyses_api.py tests/test_charts_analyze.py -v`
Expected: PASS (전체)

- [ ] **Step 7: 백엔드 전체 회귀**

Run: `python -m pytest tests/ -q`
Expected: PASS (기존 ~250 + 신규, 실패 0)

- [ ] **Step 8: 커밋**

```bash
git add app/routers/charts.py tests/test_charts_analyze.py tests/test_charts_analyses_api.py
git commit -m "feat(charts): AI 분석 자동 저장 + 히스토리 GET/DELETE 엔드포인트"
```

---

## Task 5: 프론트 — react-markdown 렌더 + 히스토리 UI

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/pages/AssetDetail.tsx`

- [ ] **Step 1: react-markdown 설치**

Run:
```bash
cd frontend && npm install react-markdown
```
Expected: `package.json` dependencies에 `react-markdown` 추가, 설치 성공.

- [ ] **Step 2: api.ts — 타입 + 함수 추가**

Modify `frontend/src/api.ts` — 타입 정의부에 추가(다른 `export type`/`interface` 옆):

```typescript
export type AssetAnalysis = {
  id: number;
  asset_id: number;
  content_md: string;
  model: string;
  trigger: string;
  created_at: string;
};
```

`analyzeChart`를 응답 확장형으로 교체하고, 두 함수 추가(`api` 객체 내 chart 관련 항목 근처):

```typescript
  analyzeChart: (id: number) =>
    j<{ analysis: string; id: number; created_at: string }>(`/api/charts/${id}/analyze`, { method: "POST" }),
  listAnalyses: (id: number, limit = 20) =>
    j<AssetAnalysis[]>(`/api/charts/${id}/analyses?limit=${limit}`),
  deleteAnalysis: (id: number) =>
    j<{ ok: boolean }>(`/api/charts/analyses/${id}`, { method: "DELETE" }),
```

(`j` 헬퍼·기존 호출 패턴은 파일 내 다른 항목과 동일하게 맞춘다.)

- [ ] **Step 3: AssetDetail.tsx — import + 상태 + 로더**

Modify `frontend/src/pages/AssetDetail.tsx`:

상단 import에 추가:

```typescript
import ReactMarkdown from "react-markdown";
import type { AssetAnalysis } from "../api";
```

`const [analysis, setAnalysis] = useState("");` 줄을 히스토리 상태로 교체:

```typescript
  const [analyses, setAnalyses] = useState<AssetAnalysis[]>([]);
  const [openIds, setOpenIds] = useState<Set<number>>(new Set());
```

종목 로드 effect(예: `api.assetDetail(...)` 호출하는 `useEffect`) 안에서 히스토리도 로드:

```typescript
    api.listAnalyses(assetId).then(setAnalyses).catch(() => setAnalyses([]));
```

(assetId 의존성 effect에 추가. assetId가 number임을 보장하는 기존 가드 안에 둔다.)

- [ ] **Step 4: AssetDetail.tsx — analyze 핸들러를 히스토리 prepend로 교체**

`analyze` 함수를 교체(분석 후 목록 새로고침 또는 prepend):

```typescript
  const analyze = async () => {
    if (!assetId) return;
    setAnalyzing(true); setMsg("");
    try {
      await api.analyzeChart(assetId);
      const rows = await api.listAnalyses(assetId);
      setAnalyses(rows);
      if (rows[0]) setOpenIds(new Set([rows[0].id]));   // 최신 1건 펼침
    } catch (e: any) {
      setMsg("분석 실패: " + e.message);
    } finally {
      setAnalyzing(false);
    }
  };
```

- [ ] **Step 5: AssetDetail.tsx — 렌더 영역 교체**

기존 분석 표시 블록(아래 형태)을:

```jsx
      {analysis && (
        <div className="card bg-surface-2 whitespace-pre-wrap text-sm leading-relaxed max-w-3xl">{analysis}</div>
      )}
```

다음으로 교체(최신 1건 펼침 + 과거 접이식 + 마크다운 렌더). 최신 항목은 마운트 시 자동 펼침을 위해, 목록 로드 시 `openIds`에 첫 항목을 포함하도록 Step 3 로더를 보강하거나 아래처럼 `idx === 0` 기본 펼침 처리:

```jsx
      {analyses.length > 0 && (
        <div className="space-y-2 max-w-3xl">
          {analyses.map((row, idx) => {
            const open = openIds.has(row.id) || idx === 0;
            const ts = new Date(row.created_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
            return (
              <div key={row.id} className="card bg-surface-2">
                <button
                  className="flex items-center justify-between w-full text-left text-xs text-muted"
                  onClick={() =>
                    setOpenIds((s) => {
                      const n = new Set(s);
                      n.has(row.id) ? n.delete(row.id) : n.add(row.id);
                      if (idx === 0 && !n.has(row.id)) n.add(-1);  // 최신 강제펼침 해제용 토글
                      return n;
                    })
                  }
                >
                  <span>{ts} · {row.trigger === "scheduled" ? "자동" : "수동"}{idx === 0 ? " · 최신" : ""}</span>
                  <span>{open ? "▲" : "▼"}</span>
                </button>
                {open && (
                  <div className="prose prose-sm prose-invert max-w-none mt-2 text-sm leading-relaxed
                                  [&_h2]:font-semibold [&_h2]:mt-3 [&_ul]:list-disc [&_ul]:pl-5">
                    <ReactMarkdown>{row.content_md}</ReactMarkdown>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
```

> 주: 위 `idx === 0` 강제펼침은 단순화를 위한 것. 토글 로직이 번잡하면, Step 3 로더에서 `setOpenIds(new Set(rows[0] ? [rows[0].id] : []))`로 최신 1건만 펼친 상태로 초기화하고, 렌더의 `open`을 `openIds.has(row.id)`만으로 판정하는 방식(더 깔끔)을 택한다. **권장: 후자.** 그 경우 위 `|| idx === 0`와 `if (idx === 0 ...)` 줄을 제거하고, Step 3 로더를 다음으로:
>
> ```typescript
>     api.listAnalyses(assetId).then((rows) => {
>       setAnalyses(rows);
>       setOpenIds(new Set(rows[0] ? [rows[0].id] : []));
>     }).catch(() => setAnalyses([]));
> ```
>
> 그리고 Step 4의 analyze 핸들러도 동일하게 `setOpenIds(new Set(rows[0] ? [rows[0].id] : []))`로 통일.

- [ ] **Step 6: 타입체크 + 빌드**

Run:
```bash
cd frontend && npx tsc --noEmit && npm run build
```
Expected: 타입 에러 0, 빌드 성공.

- [ ] **Step 7: 브라우저 검증(preview)**

dev 서버를 띄우고(`preview_start`) 종목 상세로 이동해:
- `AI 분석` 클릭 → 결과가 **마크다운으로 렌더**(헤더/굵게/불릿이 서식으로 보이고 `<b>` 등 태그가 글자로 보이지 않음)되는지 `preview_snapshot`/`preview_screenshot`로 확인.
- 새로고침 후에도 히스토리가 남고 과거 항목 접기/펼치기가 동작하는지 확인.
- 콘솔 에러 없음(`preview_console_logs`).

(AI 게이트웨이 미설정 환경이면 분석 호출은 409가 나므로, 저장·렌더 검증은 DB에 더미 분석 행을 넣거나 게이트웨이 설정 후 수행. 최소한 히스토리 GET 렌더와 마크다운 렌더는 더미 행으로 확인.)

- [ ] **Step 8: 커밋**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/api.ts frontend/src/pages/AssetDetail.tsx
git commit -m "feat(web): 종목 AI 분석 마크다운 렌더 + 접이식 히스토리 목록"
```

---

## Self-Review (작성자 체크 결과)

- **Spec 커버리지:** 출력 정규화(Task 2) · 신규 테이블(Task 1) · store/prune N=20(Task 1) · 자동 저장 웹(Task 4)·텔레그램(Task 3) · GET/DELETE API(Task 4) · 마크다운 렌더+히스토리 UI(Task 5) · 테스트(각 Task) — spec 전 항목 매핑됨.
- **타입 일관성:** `analyze_raw` → `(text, model)` 튜플 반환을 Task 2에서 정의, Task 3(dispatch)·Task 4(router)에서 동일하게 unpack. `create_and_prune(db, asset_id, content_md, model, trigger, keep=)` 시그니처를 Task 1 정의 후 Task 3·4에서 동일 사용. `AssetAnalysis` 타입 필드(id/asset_id/content_md/model/trigger/created_at)가 API 응답(Task 4 Step 5)과 일치.
- **플레이스홀더:** 없음. 모든 코드 단계에 실제 코드 포함.
- **주의:** Task 5는 프론트 자동 테스트가 없어 tsc/build + preview 수동 검증으로 대체. 기존 `analysis` 단일 상태를 제거하므로, `AssetDetail.tsx` 내 `analysis`/`setAnalysis`를 참조하는 다른 위치가 있으면 함께 정리(grep 확인).
