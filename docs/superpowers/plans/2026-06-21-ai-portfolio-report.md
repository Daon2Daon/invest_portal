# AI 포트폴리오 리포트 (3단계 B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 보유 포트폴리오를 LLM이 분석해 진단+추세+방향제안 종합 리포트를 생성·저장하고, 화면·텔레그램·자동스케줄로 제공한다.

**Architecture:** 신규 `app/services/ai_report/` 패키지(데이터수집→생성→저장→발송)를 두고, 기존 `ai_gateway` 연결·`schedules` 테이블·텔레그램·스케줄러 디스패처를 재사용한다. 데이터는 마크다운 텍스트 블록으로 LLM에 주입한다.

**Tech Stack:** FastAPI + async SQLAlchemy 2.0 + asyncpg + PostgreSQL(invest 스키마), httpx(Gemini passthrough), React 18 + Vite + TS. 테스트 pytest(asyncio).

**테스트 실행 명령(전 과제 공통):**
```bash
SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q
```

---

## 파일 구조

**백엔드 (신규):**
- `app/models/ai_report.py` — `AIReport` 모델(ai_reports 테이블)
- `app/services/ai/telegram_md.py` — md→텔레그램 HTML 변환·길이분할(차트에서 추출, 공용)
- `app/services/ai_report/__init__.py`
- `app/services/ai_report/report_data.py` — 포트폴리오+추세+종목수익률 → 마크다운 입력 블록
- `app/services/ai_report/report_generator.py` — 설정 게이팅·프롬프트·LLM 호출·create_report
- `app/services/ai_report/report_store.py` — ai_reports CRUD
- `app/services/ai_report/report_dispatch.py` — 리포트 텔레그램 발송
- `app/routers/reports.py` — `/api/reports` CRUD·send-telegram·schedule

**백엔드 (수정):**
- `app/models/__init__.py` — AIReport 등록
- `app/services/ai/llm_client.py` — `generate_text` 추가
- `app/services/ai/chart_analyzer.py` — telegram_md 헬퍼 사용(동작 동일)
- `app/services/scheduler/schedule_store.py` — `FEATURE_REPORT` 상수
- `app/services/scheduler/handlers.py` — `handle_ai_report` + 레지스트리 등록
- `app/routers/settings.py` — `/ai-report` GET/PUT
- `app/main.py` — reports 라우터 등록

**프론트 (신규/수정):**
- `frontend/src/pages/Reports.tsx` (신규)
- `frontend/src/api.ts` (수정) — 리포트 엔드포인트
- `frontend/src/App.tsx` (수정) — `/reports` 라우트
- `frontend/src/components/AppShell.tsx` (수정) — "리포트" 메뉴
- `frontend/src/pages/Settings.tsx` (수정) — AI 리포트 섹션 + 스케줄

**테스트 (신규/수정):**
- `tests/test_ai_llm_client.py` (수정) — generate_text
- `tests/test_telegram_md.py` (신규)
- `tests/test_report_data.py` (신규)
- `tests/test_report_generator.py` (신규)
- `tests/test_report_store.py` (신규)
- `tests/test_reports_api.py` (신규)
- `tests/test_reports_schedule.py` (신규)

---

## Task 1: AIReport 모델 + 테이블 생성

**Files:**
- Create: `app/models/ai_report.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_report_store.py` (이 과제에선 테이블 생성만 검증; CRUD는 Task 8)

- [ ] **Step 1: 모델 작성**

`app/models/ai_report.py`:
```python
from datetime import datetime
from sqlalchemy import Text, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class AIReport(Base):
    __tablename__ = "ai_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False, default="")
    trigger: Mapped[str] = mapped_column(String, nullable=False, default="manual")  # manual | scheduled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: __init__ 등록**

`app/models/__init__.py`에 import·__all__ 추가:
```python
from app.models.ai_report import AIReport
```
그리고 `__all__` 리스트 끝에 `"AIReport"` 추가.

- [ ] **Step 3: 테이블 생성 테스트 작성**

`tests/test_report_store.py` (신규):
```python
import pytest
from sqlalchemy import inspect


@pytest.mark.asyncio
async def test_ai_reports_table_created(db_session):
    def _has(conn):
        return inspect(conn).has_table("ai_reports", schema=None)
    engine = db_session.bind
    async with engine.connect() as conn:
        exists = await conn.run_sync(_has)
    assert exists is True
```

- [ ] **Step 4: 테스트 실행(통과)**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_report_store.py -v`
Expected: PASS (conftest가 create_all로 테이블 생성)

- [ ] **Step 5: 커밋**
```bash
git add app/models/ai_report.py app/models/__init__.py tests/test_report_store.py
git commit -m "feat(report): ai_reports 모델 + 테이블"
```

---

## Task 2: llm_client.generate_text (텍스트 전용)

**Files:**
- Modify: `app/services/ai/llm_client.py`
- Test: `tests/test_ai_llm_client.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_ai_llm_client.py` 끝에 추가:
```python
@pytest.mark.asyncio
async def test_generate_text_builds_gemini_request():
    resp = MagicMock(status_code=200)
    resp.json = MagicMock(return_value={"candidates": [{"content": {"parts": [{"text": "리포트본문"}]}}]})
    cm, client = _mock_client(resp)
    with patch("app.services.ai.llm_client.httpx.AsyncClient", return_value=cm):
        out = await lc.generate_text(
            base_url="http://gw", api_key="K", model="gemini/gemini-2.5-flash",
            prompt="프롬프트", temperature=0.5, max_output_tokens=4000)
    assert out == "리포트본문"
    args, kwargs = client.post.call_args
    assert args[0] == "http://gw/gemini/v1beta/models/gemini-2.5-flash:generateContent"
    assert kwargs["params"] == {"key": "K"}
    parts = kwargs["json"]["contents"][0]["parts"]
    assert parts[0]["text"] == "프롬프트"
    assert kwargs["json"]["generationConfig"]["maxOutputTokens"] == 4000


@pytest.mark.asyncio
async def test_generate_text_non200_raises():
    resp = MagicMock(status_code=500, text="boom")
    cm, _ = _mock_client(resp)
    with patch("app.services.ai.llm_client.httpx.AsyncClient", return_value=cm):
        with pytest.raises(lc.LiteLLMError):
            await lc.generate_text(base_url="http://gw", api_key="K", model="m", prompt="p")


@pytest.mark.asyncio
async def test_generate_text_missing_base_url_raises():
    with pytest.raises(lc.LiteLLMError):
        await lc.generate_text(base_url="", api_key="K", model="m", prompt="p")
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_ai_llm_client.py::test_generate_text_builds_gemini_request -v`
Expected: FAIL (`AttributeError: ... has no attribute 'generate_text'`)

- [ ] **Step 3: 구현**

`app/services/ai/llm_client.py`에서 `list_models` 위(또는 `analyze_images` 아래)에 추가:
```python
async def generate_text(base_url: str, api_key: str, model: str, prompt: str,
                        temperature: float | None = None,
                        max_output_tokens: int | None = None) -> str:
    """텍스트 프롬프트 → Gemini generateContent 텍스트 응답. 실패 시 LiteLLMError."""
    base = _normalize_base_url(base_url)
    if not base:
        raise LiteLLMError("AI Gateway base_url이 비어 있습니다.")
    if not api_key:
        raise LiteLLMError("AI Gateway api_key가 비어 있습니다.")
    model_id = model.split("/")[-1] if "/" in model else model
    url = f"{base}/gemini/v1beta/models/{model_id}:generateContent"
    body: dict = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    gen_cfg: dict = {}
    if temperature is not None:
        gen_cfg["temperature"] = temperature
    if max_output_tokens is not None:
        gen_cfg["maxOutputTokens"] = max_output_tokens
    if gen_cfg:
        body["generationConfig"] = gen_cfg
    try:
        async with httpx.AsyncClient(timeout=_GEMINI_TIMEOUT) as client:
            resp = await client.post(url, params={"key": api_key}, json=body)
            if resp.status_code != 200:
                raise LiteLLMError(f"Gemini 텍스트 생성 실패: {resp.status_code} - {resp.text}")
            text = _pick_text_from_gemini(resp.json())
    except httpx.RequestError as e:
        raise LiteLLMError(f"AI Gateway 연결 실패: {e}") from e
    if not text:
        raise LiteLLMError("Gemini 응답에서 텍스트를 찾지 못했습니다.")
    return text
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_ai_llm_client.py -v`
Expected: PASS (전체)

- [ ] **Step 5: 커밋**
```bash
git add app/services/ai/llm_client.py tests/test_ai_llm_client.py
git commit -m "feat(report): llm_client.generate_text 텍스트 전용 생성"
```

---

## Task 3: telegram_md 공용 헬퍼 추출 (차트 회귀 없음)

**Files:**
- Create: `app/services/ai/telegram_md.py`
- Modify: `app/services/ai/chart_analyzer.py`
- Test: `tests/test_telegram_md.py`

- [ ] **Step 1: 헬퍼 모듈 작성**

`app/services/ai/telegram_md.py`:
```python
"""마크다운 → 텔레그램 HTML 변환 + 길이 분할. 차트 분석·AI 리포트가 공유."""
import re


def md_to_telegram_html(text: str) -> str:
    text = re.sub(r"```[a-zA-Z]*\n?([\s\S]*?)```", r"<pre>\1</pre>", text)
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*([^*\n]+)\*", r"<i>\1</i>", text)
    text = re.sub(r"^#{1,3}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"<(h[1-6]|ul|ol|li|hr|br|div|span|p)\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</(h[1-6]|ul|ol|li|hr|br|div|span|p)\b>", "", text, flags=re.IGNORECASE)
    return text.strip()


def split_message(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, current, current_len = [], [], 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > limit and current:
            parts.append("".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += len(line)
    if current:
        parts.append("".join(current))
    return parts
```

- [ ] **Step 2: chart_analyzer가 헬퍼를 쓰도록 수정**

`app/services/ai/chart_analyzer.py`:
- import 추가: `from app.services.ai import telegram_md`
- `_md_to_telegram_html` 함수 정의와 `_split_message` 함수 정의를 **삭제**.
- 파일 마지막 `analyze` 함수의 마지막 줄을 교체:
```python
    raw = await analyze_raw(db, images, ticker, name, market)
    return telegram_md.split_message(telegram_md.md_to_telegram_html(raw))
```

- [ ] **Step 3: 헬퍼 테스트 작성**

`tests/test_telegram_md.py`:
```python
from app.services.ai import telegram_md as tm


def test_md_to_html_converts_headings_and_bold():
    out = tm.md_to_telegram_html("# 제목\n**굵게** *기울임*")
    assert "<b>제목</b>" in out
    assert "<b>굵게</b>" in out
    assert "<i>기울임</i>" in out


def test_md_to_html_strips_unsupported_tags():
    out = tm.md_to_telegram_html("<div>x</div>")
    assert "<div>" not in out and "x" in out


def test_split_message_short_returns_single():
    assert tm.split_message("abc", limit=10) == ["abc"]


def test_split_message_splits_on_lines():
    text = "a\n" * 10
    parts = tm.split_message(text, limit=5)
    assert len(parts) > 1
    assert "".join(parts) == text
```

- [ ] **Step 4: 회귀 포함 테스트 실행**

Run: `.venv/bin/pytest tests/test_telegram_md.py tests/test_chart_analyzer.py -v`
Expected: PASS (헬퍼 신규 + 기존 차트 분석 테스트 그대로 통과)

- [ ] **Step 5: 커밋**
```bash
git add app/services/ai/telegram_md.py app/services/ai/chart_analyzer.py tests/test_telegram_md.py
git commit -m "refactor(ai): md→텔레그램 HTML 헬퍼를 telegram_md로 추출(공용)"
```

---

## Task 4: report_data 순수 함수 (pct_change + build_input_block)

**Files:**
- Create: `app/services/ai_report/__init__.py` (빈 파일)
- Create: `app/services/ai_report/report_data.py`
- Test: `tests/test_report_data.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_report_data.py`:
```python
from app.services.ai_report import report_data as rd


def test_pct_change_basic():
    assert rd.pct_change([100, 110], 1) == pytest.approx(10.0)
    assert rd.pct_change([100, 90], 1) == pytest.approx(-10.0)


def test_pct_change_insufficient_returns_none():
    assert rd.pct_change([100], 1) is None
    assert rd.pct_change([], 5) is None


def test_build_input_block_contains_sections():
    portfolio = {
        "summary": {"total_value_krw": 1000.0, "total_cost_krw": 600.0,
                    "total_profit_loss_krw": 400.0, "total_profit_loss_pct": 66.7,
                    "total_cash_krw": 100.0},
        "allocation": [{"asset_class": "주식", "value_krw": 600.0, "weight_pct": 60.0},
                       {"asset_class": "현금성", "value_krw": 100.0, "weight_pct": 10.0}],
        "positions": [{"asset_id": 1, "ticker": "005930", "name": "삼성전자",
                       "asset_class": "주식", "value_krw": 600.0, "weight_pct": 60.0,
                       "profit_loss_krw": 100.0, "profit_loss_pct": 20.0}],
    }
    trend = [{"date": "2026-06-20", "total_value_krw": 990.0, "total_pl_krw": 390.0}]
    returns = {1: {"w1": 1.5, "m1": -3.0}}
    block = rd.build_input_block(portfolio, trend, returns, today="2026-06-21")
    assert "2026-06-21" in block
    assert "삼성전자" in block and "005930" in block
    assert "주식" in block
    assert "1.5%" in block and "-3.0%" in block
    assert "2026-06-20" in block


def test_build_input_block_no_history_fallback():
    portfolio = {
        "summary": {"total_value_krw": 100.0, "total_cost_krw": 100.0,
                    "total_profit_loss_krw": 0.0, "total_profit_loss_pct": 0.0,
                    "total_cash_krw": 0.0},
        "allocation": [],
        "positions": [{"asset_id": 9, "ticker": "X", "name": "수동채권",
                       "asset_class": "채권", "value_krw": 100.0, "weight_pct": 100.0,
                       "profit_loss_krw": 0.0, "profit_loss_pct": 0.0}],
    }
    block = rd.build_input_block(portfolio, [], {9: None}, today="2026-06-21")
    assert "(이력 없음)" in block
```
파일 상단에 `import pytest` 추가.

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_report_data.py -v`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: 구현**

`app/services/ai_report/__init__.py` (빈 파일 생성).

`app/services/ai_report/report_data.py`:
```python
"""포트폴리오·추세·종목수익률 → LLM 입력용 마크다운 블록. 수집 + 순수 변환."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset
from app.services.portfolio.portfolio_service import get_portfolio
from app.services.market.history_service import get_history
from app.services.snapshot import snapshot_store

_KST = ZoneInfo("Asia/Seoul")
_TREND_DAYS = 30      # 추세 표에 포함할 스냅샷 범위(일)
_HISTORY_DAYS = 45    # 종목 수익률 산정용 일봉 조회 범위(거래일 ~20 확보)
_W1, _M1 = 5, 20      # 최근 1주/1달 거래일 수


def pct_change(closes: list[float], periods: int) -> float | None:
    """종가 리스트에서 마지막 대비 periods 거래일 전 변동률(%). 부족하면 None."""
    if len(closes) <= periods:
        return None
    prev = closes[-1 - periods]
    if not prev:
        return None
    return (closes[-1] / prev - 1) * 100


def _fmt(n: float) -> str:
    return f"{n:,.0f}"


def _ret(v: float | None) -> str:
    return f"{v:+.1f}%" if v is not None else "(이력 없음)"


def build_input_block(portfolio: dict, trend: list[dict],
                      returns: dict[int, dict | None], today: str) -> str:
    """수집된 데이터 → 마크다운 입력 블록(순수)."""
    s = portfolio["summary"]
    lines: list[str] = []
    lines.append(f"## 포트폴리오 종합 데이터 ({today} 기준, 통화 KRW)\n")

    lines.append("### 요약")
    lines.append(f"- 총자산: {_fmt(s['total_value_krw'])}")
    lines.append(f"- 투자원금: {_fmt(s['total_cost_krw'])}")
    lines.append(f"- 평가손익: {s['total_profit_loss_krw']:+,.0f} ({s['total_profit_loss_pct']:+.1f}%)")
    lines.append(f"- 현금성: {_fmt(s['total_cash_krw'])}\n")

    lines.append("### 자산군별 비중")
    lines.append("| 자산군 | 평가액 | 비중 |")
    lines.append("|---|---|---|")
    for a in portfolio["allocation"]:
        lines.append(f"| {a['asset_class']} | {_fmt(a['value_krw'])} | {a['weight_pct']:.1f}% |")
    lines.append("")

    lines.append("### 보유 종목")
    lines.append("| 종목 | 자산군 | 평가액 | 비중 | 손익 | 최근1주 | 최근1달 |")
    lines.append("|---|---|---|---|---|---|---|")
    for p in portfolio["positions"]:
        r = returns.get(p["asset_id"]) or {}
        w1 = _ret(r.get("w1")) if r else "(이력 없음)"
        m1 = _ret(r.get("m1")) if r else "(이력 없음)"
        lines.append(
            f"| {p['name']}({p['ticker']}) | {p['asset_class']} | {_fmt(p['value_krw'])} | "
            f"{p['weight_pct']:.1f}% | {p['profit_loss_pct']:+.1f}% | {w1} | {m1} |"
        )
    lines.append("")

    lines.append("### 최근 자산 추세 (일별 스냅샷)")
    if trend:
        lines.append("| 날짜 | 총자산 | 평가손익 |")
        lines.append("|---|---|---|")
        for t in trend:
            lines.append(f"| {t['date']} | {_fmt(t['total_value_krw'])} | {t['total_pl_krw']:+,.0f} |")
    else:
        lines.append("(누적된 스냅샷이 없어 추세를 제공할 수 없습니다.)")
    lines.append("")
    return "\n".join(lines)


async def _position_returns(db: AsyncSession, positions: list[dict]) -> dict[int, dict | None]:
    """종목별 최근 1주/1달 수익률. 실패·무이력은 None(폴백)."""
    out: dict[int, dict | None] = {}
    for p in positions:
        asset = await db.get(Asset, p["asset_id"])
        if asset is None:
            out[p["asset_id"]] = None
            continue
        try:
            df = await get_history(asset, _HISTORY_DAYS)
        except Exception:
            df = None
        if df is None or "Close" not in getattr(df, "columns", []):
            out[p["asset_id"]] = None
            continue
        closes = [float(x) for x in df["Close"].tolist()]
        w1 = pct_change(closes, _W1)
        m1 = pct_change(closes, _M1)
        out[p["asset_id"]] = None if (w1 is None and m1 is None) else {"w1": w1, "m1": m1}
    return out


async def collect_input_block(db: AsyncSession) -> str:
    """포트폴리오·추세·종목수익률을 모아 마크다운 입력 블록을 만든다."""
    portfolio = await get_portfolio(db)
    today = datetime.now(_KST).date()
    since = today - timedelta(days=_TREND_DAYS)
    snaps = await snapshot_store.list_snapshots(db, since)
    trend = [
        {"date": r.date.isoformat(),
         "total_value_krw": float(r.total_value_krw),
         "total_pl_krw": float(r.total_pl_krw)}
        for r in snaps
    ]
    returns = await _position_returns(db, portfolio["positions"])
    return build_input_block(portfolio, trend, returns, today.isoformat())
```

> 참고: `snapshot_store.list_snapshots(db, since)`는 since 이상 날짜를 오름차순으로 반환한다(Task A에서 구현됨). `_position_returns`의 반환값은 종목별로 `{"w1":..,"m1":..}` 또는 `None`이며, `build_input_block`은 둘 다 처리한다.

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_report_data.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**
```bash
git add app/services/ai_report/__init__.py app/services/ai_report/report_data.py tests/test_report_data.py
git commit -m "feat(report): report_data 입력 블록 구성(순수 변환 + 수집)"
```

---

## Task 5: report_store CRUD

**Files:**
- Create: `app/services/ai_report/report_store.py`
- Test: `tests/test_report_store.py` (Task 1 파일에 추가)

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_report_store.py`에 추가:
```python
from app.services.ai_report import report_store


@pytest.mark.asyncio
async def test_create_and_list_and_get_and_delete(db_session):
    r1 = await report_store.create(db_session, "리포트A", "## 본문A", "gemini/x", "manual")
    r2 = await report_store.create(db_session, "리포트B", "## 본문B", "gemini/x", "scheduled")
    rows = await report_store.list_reports(db_session)
    assert [r.id for r in rows][:2] == [r2.id, r1.id]   # 최신순
    got = await report_store.get_report(db_session, r1.id)
    assert got is not None and got.content_md == "## 본문A"
    assert await report_store.delete_report(db_session, r1.id) is True
    assert await report_store.get_report(db_session, r1.id) is None
    assert await report_store.delete_report(db_session, 999999) is False
```

- [ ] **Step 2: 실패 확인**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_report_store.py::test_create_and_list_and_get_and_delete -v`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: 구현**

`app/services/ai_report/report_store.py`:
```python
"""ai_reports 테이블 CRUD."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIReport


async def create(db: AsyncSession, title: str, content_md: str,
                 model: str, trigger: str) -> AIReport:
    row = AIReport(title=title, content_md=content_md, model=model, trigger=trigger)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_reports(db: AsyncSession, limit: int = 100) -> list[AIReport]:
    res = await db.execute(
        select(AIReport).order_by(AIReport.id.desc()).limit(limit)
    )
    return list(res.scalars().all())


async def get_report(db: AsyncSession, report_id: int) -> AIReport | None:
    return await db.get(AIReport, report_id)


async def delete_report(db: AsyncSession, report_id: int) -> bool:
    row = await db.get(AIReport, report_id)
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True
```

- [ ] **Step 4: 통과 확인**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_report_store.py -v`
Expected: PASS (전체)

- [ ] **Step 5: 커밋**
```bash
git add app/services/ai_report/report_store.py tests/test_report_store.py
git commit -m "feat(report): report_store CRUD"
```

---

## Task 6: report_generator (게이팅 + 생성)

**Files:**
- Create: `app/services/ai_report/report_generator.py`
- Test: `tests/test_report_generator.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_report_generator.py`:
```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.ai_report import report_generator as rg


def _settings(values: dict):
    async def fake(db, category, key):
        return values.get((category, key))
    return fake


@pytest.mark.asyncio
async def test_load_config_disabled_raises():
    vals = {("ai_report", "enabled"): "false"}
    with patch("app.services.ai_report.report_generator.get_setting", _settings(vals)):
        with pytest.raises(rg.ReportDisabled):
            await rg.load_config(MagicMock())


@pytest.mark.asyncio
async def test_load_config_missing_keys_raises():
    vals = {("ai_report", "enabled"): "true", ("ai_gateway", "base_url"): "http://gw"}
    with patch("app.services.ai_report.report_generator.get_setting", _settings(vals)):
        with pytest.raises(rg.ReportNotConfigured):
            await rg.load_config(MagicMock())


@pytest.mark.asyncio
async def test_load_config_ok_uses_default_prompt():
    vals = {("ai_report", "enabled"): "true",
            ("ai_gateway", "base_url"): "http://gw",
            ("ai_gateway", "api_key"): "K",
            ("ai_report", "model"): "gemini/x"}
    with patch("app.services.ai_report.report_generator.get_setting", _settings(vals)):
        cfg = await rg.load_config(MagicMock())
    assert cfg["base_url"] == "http://gw" and cfg["model"] == "gemini/x"
    assert cfg["prompt"] == rg.DEFAULT_PROMPT


@pytest.mark.asyncio
async def test_generate_markdown_calls_llm():
    cfg = {"base_url": "http://gw", "api_key": "K", "model": "gemini/x", "prompt": "지시"}
    with patch("app.services.ai_report.report_generator.load_config", AsyncMock(return_value=cfg)), \
         patch("app.services.ai_report.report_generator.report_data.collect_input_block",
               AsyncMock(return_value="## 데이터블록")), \
         patch("app.services.ai_report.report_generator.llm_client.generate_text",
               AsyncMock(return_value="## 리포트")) as gt:
        md, model = await rg.generate_markdown(MagicMock())
    assert md == "## 리포트" and model == "gemini/x"
    prompt_arg = gt.call_args.kwargs["prompt"]
    assert "지시" in prompt_arg and "## 데이터블록" in prompt_arg


@pytest.mark.asyncio
async def test_create_report_stores_row():
    with patch("app.services.ai_report.report_generator.generate_markdown",
               AsyncMock(return_value=("## 리포트", "gemini/x"))), \
         patch("app.services.ai_report.report_generator.report_store.create",
               AsyncMock(return_value="ROW")) as cr:
        out = await rg.create_report(MagicMock(), trigger="scheduled")
    assert out == "ROW"
    assert cr.call_args.args[4] == "scheduled"   # trigger 인자
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_report_generator.py -v`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: 구현**

`app/services/ai_report/report_generator.py`:
```python
"""포트폴리오 데이터 → LLM 종합 리포트(마크다운). 설정: 연결=ai_gateway, 모델/프롬프트/토글=ai_report."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings.settings_manager import get_setting
from app.services.ai import llm_client
from app.services.ai_report import report_data, report_store

CONN = "ai_gateway"      # base_url/api_key 공유
REPORT = "ai_report"     # model/prompt/enabled 전용
_TEMPERATURE = 0.5
_MAX_OUTPUT_TOKENS = 4000
_KST = ZoneInfo("Asia/Seoul")


class ReportNotConfigured(Exception):
    pass


class ReportDisabled(Exception):
    pass


DEFAULT_PROMPT = """# 역할
- 당신은 개인 투자자의 자산운용을 돕는 포트폴리오 애널리스트입니다.
- 아래에 제공되는 포트폴리오 데이터(요약·자산군 비중·보유 종목·일별 추세)만을 근거로 한국어 종합 리포트를 작성합니다.
- 매크로/뉴스/외부 지식은 사용하지 말고, 주어진 데이터에서 읽히는 사실만 인용합니다.

# 출력 구조 (이 순서·헤더 유지, 마크다운)
1. **종합 진단** — 총자산·손익 현황, 포트폴리오의 전반적 성격 한두 줄.
2. **자산군 배분 진단** — 편중/집중 위험. 특정 자산군·단일 종목 비중이 큰지, 현금성 비중이 적정한지 사실 환기.
3. **추세·성과 리뷰** — 제공된 일별 스냅샷이 2개 이상이면 총자산·손익의 최근 변화를 서술. 1개 이하이면 "추세 데이터 부족"이라고 명시.
4. **종목별 관찰** — 비중이 크거나 손익/최근 수익률이 두드러진 종목 위주로. (이력 없음) 종목은 수익률 언급을 생략.
5. **방향 제안** — 관찰에 근거한 점검 방향(예: 비중 편중 점검, 현금 비중 재고). 구체적 매매 지시(무엇을 몇 % 사라/팔라)는 하지 않습니다.

# 작성 원칙
- 개조식(불릿) 위주, 숫자는 데이터에 제시된 값을 인용.
- 단정적 예측 대신 조건/관찰형으로 서술.
- 분량: 한글 1,200~2,000자 권장."""

_DISCLAIMER = "\n\n---\n*본 리포트는 보유 데이터에 기반한 참고용 분석이며 투자 권유가 아닙니다.*"


async def load_config(db: AsyncSession) -> dict:
    enabled = (await get_setting(db, REPORT, "enabled")) or "false"
    if enabled.lower() != "true":
        raise ReportDisabled("AI 리포트가 비활성화되어 있습니다.")
    base_url = await get_setting(db, CONN, "base_url")
    api_key = await get_setting(db, CONN, "api_key")
    model = await get_setting(db, REPORT, "model")
    if not base_url or not api_key or not model:
        raise ReportNotConfigured("AI 게이트웨이 연결(base_url/api_key)·리포트 모델 설정이 필요합니다.")
    prompt = (await get_setting(db, REPORT, "prompt")) or DEFAULT_PROMPT
    return {"base_url": base_url, "api_key": api_key, "model": model, "prompt": prompt}


async def generate_markdown(db: AsyncSession) -> tuple[str, str]:
    """(마크다운 본문, 사용 모델). 미설정/비활성/LLM 실패는 예외 전파."""
    cfg = await load_config(db)
    block = await report_data.collect_input_block(db)
    full_prompt = f"{cfg['prompt']}\n\n# 입력 데이터\n{block}"
    md = await llm_client.generate_text(
        base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"],
        prompt=full_prompt, temperature=_TEMPERATURE, max_output_tokens=_MAX_OUTPUT_TOKENS)
    return md + _DISCLAIMER, cfg["model"]


async def create_report(db: AsyncSession, trigger: str):
    """생성 + 저장. AIReport 반환."""
    md, model = await generate_markdown(db)
    title = f"{datetime.now(_KST).date().isoformat()} 포트폴리오 종합 리포트"
    return await report_store.create(db, title, md, model, trigger)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_report_generator.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**
```bash
git add app/services/ai_report/report_generator.py tests/test_report_generator.py
git commit -m "feat(report): report_generator 게이팅·프롬프트·생성"
```

---

## Task 7: report_dispatch (텔레그램 발송)

**Files:**
- Create: `app/services/ai_report/report_dispatch.py`
- Test: `tests/test_reports_api.py` (dispatch 단위 테스트를 여기 포함)

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_reports_api.py` (신규, 우선 dispatch 테스트만):
```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.ai_report import report_dispatch


@pytest.mark.asyncio
async def test_send_report_splits_and_sends():
    report = MagicMock(content_md="**제목**\n본문")
    with patch("app.services.ai_report.report_dispatch.telegram_service.send_message",
               AsyncMock(return_value=True)) as sm, \
         patch("app.services.ai_report.report_dispatch.asyncio.sleep", AsyncMock()):
        sent = await report_dispatch.send_report(MagicMock(), report)
    assert sent == 1
    assert "<b>제목</b>" in sm.call_args.args[1]
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_reports_api.py::test_send_report_splits_and_sends -v`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: 구현**

`app/services/ai_report/report_dispatch.py`:
```python
"""AI 리포트를 텔레그램으로 발송(마크다운 → HTML, 길이 분할)."""
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIReport
from app.services.ai import telegram_md
from app.services.notification import telegram_service


async def send_report(db: AsyncSession, report: AIReport) -> int:
    """발송한 메시지 조각 수 반환. 텔레그램 미설정 시 TelegramNotConfigured 전파."""
    chunks = telegram_md.split_message(telegram_md.md_to_telegram_html(report.content_md))
    sent = 0
    for i, chunk in enumerate(chunks):
        if i > 0:
            await asyncio.sleep(2)
        if await telegram_service.send_message(db, chunk):
            sent += 1
    return sent
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_reports_api.py::test_send_report_splits_and_sends -v`
Expected: PASS

- [ ] **Step 5: 커밋**
```bash
git add app/services/ai_report/report_dispatch.py tests/test_reports_api.py
git commit -m "feat(report): report_dispatch 텔레그램 발송"
```

---

## Task 8: reports 라우터 (CRUD + send-telegram) + main 등록

**Files:**
- Create: `app/routers/reports.py`
- Modify: `app/main.py`
- Test: `tests/test_reports_api.py`

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_reports_api.py`에 추가:
```python
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.ai_report import report_generator


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _report(id=1):
    r = MagicMock()
    r.id, r.title, r.content_md, r.model, r.trigger = id, "제목", "## 본문", "gemini/x", "manual"
    r.created_at = MagicMock()
    r.created_at.isoformat = MagicMock(return_value="2026-06-21T06:30:00+09:00")
    return r


@pytest.mark.asyncio
async def test_post_report_creates():
    with patch("app.routers.reports.report_generator.create_report",
               AsyncMock(return_value=_report())):
        async with await _client() as ac:
            resp = await ac.post("/api/reports")
    assert resp.status_code == 200
    assert resp.json()["content_md"] == "## 본문"


@pytest.mark.asyncio
async def test_post_report_disabled_409():
    with patch("app.routers.reports.report_generator.create_report",
               AsyncMock(side_effect=report_generator.ReportDisabled("off"))):
        async with await _client() as ac:
            resp = await ac.post("/api/reports")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_post_report_gateway_error_502():
    from app.services.ai.llm_client import LiteLLMError
    with patch("app.routers.reports.report_generator.create_report",
               AsyncMock(side_effect=LiteLLMError("boom"))):
        async with await _client() as ac:
            resp = await ac.post("/api/reports")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_get_list_and_detail_and_delete():
    with patch("app.routers.reports.report_store.list_reports",
               AsyncMock(return_value=[_report(2), _report(1)])), \
         patch("app.routers.reports.report_store.get_report",
               AsyncMock(return_value=_report(1))), \
         patch("app.routers.reports.report_store.delete_report",
               AsyncMock(return_value=True)):
        async with await _client() as ac:
            lst = await ac.get("/api/reports")
            detail = await ac.get("/api/reports/1")
            dele = await ac.delete("/api/reports/1")
    assert len(lst.json()) == 2
    assert detail.json()["id"] == 1
    assert dele.status_code == 200


@pytest.mark.asyncio
async def test_detail_404():
    with patch("app.routers.reports.report_store.get_report", AsyncMock(return_value=None)):
        async with await _client() as ac:
            resp = await ac.get("/api/reports/999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_send_telegram_409_when_not_configured():
    from app.services.notification import telegram_service
    with patch("app.routers.reports.report_store.get_report", AsyncMock(return_value=_report(1))), \
         patch("app.routers.reports.report_dispatch.send_report",
               AsyncMock(side_effect=telegram_service.TelegramNotConfigured("no"))):
        async with await _client() as ac:
            resp = await ac.post("/api/reports/1/send-telegram")
    assert resp.status_code == 409
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_reports_api.py::test_post_report_creates -v`
Expected: FAIL (404 — 라우터 없음)

- [ ] **Step 3: 라우터 구현**

`app/routers/reports.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.ai_report import report_generator, report_store, report_dispatch
from app.services.ai.llm_client import LiteLLMError
from app.services.notification import telegram_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _serialize(r) -> dict:
    return {"id": r.id, "title": r.title, "content_md": r.content_md,
            "model": r.model, "trigger": r.trigger,
            "created_at": r.created_at.isoformat() if r.created_at else None}


@router.post("")
async def create_report(db: AsyncSession = Depends(get_db)):
    try:
        report = await report_generator.create_report(db, trigger="manual")
    except (report_generator.ReportDisabled, report_generator.ReportNotConfigured) as e:
        raise HTTPException(409, str(e))
    except LiteLLMError as e:
        raise HTTPException(502, str(e))
    return _serialize(report)


@router.get("")
async def list_reports(db: AsyncSession = Depends(get_db)):
    rows = await report_store.list_reports(db)
    return [_serialize(r) for r in rows]


@router.get("/{report_id}")
async def get_report(report_id: int, db: AsyncSession = Depends(get_db)):
    r = await report_store.get_report(db, report_id)
    if r is None:
        raise HTTPException(404, "리포트를 찾을 수 없습니다.")
    return _serialize(r)


@router.delete("/{report_id}")
async def delete_report(report_id: int, db: AsyncSession = Depends(get_db)):
    await report_store.delete_report(db, report_id)
    return {"status": "ok"}


@router.post("/{report_id}/send-telegram")
async def send_telegram(report_id: int, db: AsyncSession = Depends(get_db)):
    r = await report_store.get_report(db, report_id)
    if r is None:
        raise HTTPException(404, "리포트를 찾을 수 없습니다.")
    try:
        sent = await report_dispatch.send_report(db, r)
    except telegram_service.TelegramNotConfigured as e:
        raise HTTPException(409, str(e))
    return {"sent": sent}
```

- [ ] **Step 4: main.py 등록**

`app/main.py`:
- import 줄에 `reports` 추가:
```python
from app.routers import assets, holdings, portfolio, fx, settings as settings_router, cash, charts, watchlist, alerts, market_summary, trend, reports
```
- include_router 튜플에 `reports.router` 추가:
```python
for r in (assets.router, holdings.router, portfolio.router, fx.router, settings_router.router, cash.router, charts.router, watchlist.router, alerts.router, market_summary.router, trend.router, reports.router):
```

- [ ] **Step 5: 통과 확인**

Run: `.venv/bin/pytest tests/test_reports_api.py -v`
Expected: PASS (전체)

- [ ] **Step 6: 커밋**
```bash
git add app/routers/reports.py app/main.py tests/test_reports_api.py
git commit -m "feat(report): /api/reports 라우터(CRUD·텔레그램) + 등록"
```

---

## Task 9: 스케줄 핸들러 + 리포트 스케줄 라우트

**Files:**
- Modify: `app/services/scheduler/schedule_store.py`
- Modify: `app/services/scheduler/handlers.py`
- Modify: `app/routers/reports.py`
- Test: `tests/test_reports_schedule.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_reports_schedule.py`:
```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.scheduler import handlers
from app.services.scheduler.schedule_store import FEATURE_REPORT


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def test_feature_report_registered():
    assert FEATURE_REPORT in handlers.HANDLERS


@pytest.mark.asyncio
async def test_handle_ai_report_generates_and_sends():
    sched = MagicMock(feature_type=FEATURE_REPORT, target_id=0)
    report = MagicMock()
    with patch("app.services.scheduler.handlers.report_generator.create_report",
               AsyncMock(return_value=report)) as cr, \
         patch("app.services.scheduler.handlers.report_dispatch.send_report",
               AsyncMock(return_value=1)) as sr:
        await handlers.handle_ai_report(MagicMock(), sched)
    assert cr.call_args.kwargs["trigger"] == "scheduled"
    sr.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_ai_report_telegram_not_configured_is_swallowed():
    from app.services.notification import telegram_service
    sched = MagicMock(feature_type=FEATURE_REPORT, target_id=0)
    with patch("app.services.scheduler.handlers.report_generator.create_report",
               AsyncMock(return_value=MagicMock())), \
         patch("app.services.scheduler.handlers.report_dispatch.send_report",
               AsyncMock(side_effect=telegram_service.TelegramNotConfigured("no"))):
        await handlers.handle_ai_report(MagicMock(), sched)   # 예외 없이 통과


@pytest.mark.asyncio
async def test_report_schedule_routes():
    with patch("app.routers.reports.schedule_store.upsert_schedule", AsyncMock()) as up, \
         patch("app.routers.reports.schedule_store.get_schedule",
               AsyncMock(return_value=MagicMock(send_time="06:30", days_of_week="0,1,2,3,4", enabled=True))), \
         patch("app.routers.reports.schedule_store.delete_schedule", AsyncMock()):
        async with await _client() as ac:
            put = await ac.put("/api/reports/schedule",
                               json={"send_time": "06:30", "days_of_week": [0, 1, 2], "enabled": True})
            get = await ac.get("/api/reports/schedule")
            dele = await ac.delete("/api/reports/schedule")
    assert put.status_code == 200
    assert get.json()["send_time"] == "06:30"
    assert dele.status_code == 200
    assert up.call_args.args[1] == FEATURE_REPORT and up.call_args.args[2] == 0
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_reports_schedule.py -v`
Expected: FAIL (FEATURE_REPORT/handle_ai_report/라우트 없음)

- [ ] **Step 3: schedule_store 상수 추가**

`app/services/scheduler/schedule_store.py`의 상수 블록에 추가:
```python
FEATURE_REPORT = "ai_report"
```

- [ ] **Step 4: handlers 추가**

`app/services/scheduler/handlers.py`:
- import 추가:
```python
from app.services.ai_report import report_generator, report_dispatch
from app.services.scheduler.schedule_store import FEATURE_SUMMARY_US, FEATURE_SUMMARY_KR, FEATURE_REPORT
```
- 핸들러 함수 추가(파일 내 다른 핸들러들 옆):
```python
async def handle_ai_report(db: AsyncSession, schedule: Schedule) -> None:
    report = await report_generator.create_report(db, trigger="scheduled")
    try:
        await report_dispatch.send_report(db, report)
    except telegram_service.TelegramNotConfigured:
        _log.info("텔레그램 미설정 — AI 리포트 발송 생략(생성·저장은 완료)")
```
- HANDLERS dict에 등록:
```python
HANDLERS = {
    "chart_analysis": handle_chart_analysis,
    FEATURE_SUMMARY_US: handle_market_summary,
    FEATURE_SUMMARY_KR: handle_market_summary,
    FEATURE_REPORT: handle_ai_report,
}
```

- [ ] **Step 5: reports 라우터에 스케줄 엔드포인트 추가**

`app/routers/reports.py`:
- import 추가:
```python
import re
from pydantic import BaseModel, field_validator
from app.services.scheduler import schedule_store
from app.services.scheduler.schedule_store import FEATURE_REPORT
```
- `_serialize` 아래에 추가:
```python
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


@router.get("/schedule")
async def get_schedule(db: AsyncSession = Depends(get_db)):
    sched = await schedule_store.get_schedule(db, FEATURE_REPORT, 0)
    if sched is None:
        return None
    return {"send_time": sched.send_time,
            "days_of_week": [int(x) for x in sched.days_of_week.split(",") if x != ""],
            "enabled": sched.enabled}


@router.put("/schedule")
async def put_schedule(body: ScheduleIn, db: AsyncSession = Depends(get_db)):
    days = ",".join(str(d) for d in sorted(set(body.days_of_week)))
    await schedule_store.upsert_schedule(db, FEATURE_REPORT, 0, body.send_time, days, body.enabled)
    return {"status": "ok"}


@router.delete("/schedule")
async def delete_schedule(db: AsyncSession = Depends(get_db)):
    await schedule_store.delete_schedule(db, FEATURE_REPORT, 0)
    return {"status": "ok"}
```

> 주의(라우트 순서): `/schedule`는 리터럴 경로이고 `/{report_id}`는 동적 경로다. FastAPI는 `/{report_id}`에 `report_id: int`를 요구하므로 "schedule"은 매칭되지 않아 충돌하지 않는다. 그래도 안전을 위해 `/schedule` 라우트들을 `/{report_id}` 라우트 **위쪽**(파일에서 먼저)에 두는 것을 권장한다 — Task 8에서 만든 `/{report_id}` 핸들러보다 앞에 배치.

- [ ] **Step 6: 통과 확인**

Run: `.venv/bin/pytest tests/test_reports_schedule.py tests/test_reports_api.py -v`
Expected: PASS (전체)

- [ ] **Step 7: 커밋**
```bash
git add app/services/scheduler/schedule_store.py app/services/scheduler/handlers.py app/routers/reports.py tests/test_reports_schedule.py
git commit -m "feat(report): 자동 스케줄(handle_ai_report) + 리포트 스케줄 라우트"
```

---

## Task 10: settings /ai-report (모델/프롬프트/토글)

**Files:**
- Modify: `app/routers/settings.py`
- Test: `tests/test_settings_ai.py`

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_settings_ai.py`에 추가(파일 상단 import·헬퍼는 기존 것 재사용; 없으면 아래 형태로):
```python
@pytest.mark.asyncio
async def test_get_put_ai_report_settings():
    from httpx import AsyncClient, ASGITransport
    from unittest.mock import patch, AsyncMock
    from app.main import app

    store = {}

    async def fake_get(db, cat, key):
        return store.get((cat, key))

    async def fake_set(db, cat, key, val, is_secret=False):
        store[(cat, key)] = val

    with patch("app.routers.settings.get_setting", fake_get), \
         patch("app.routers.settings.set_setting", fake_set):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            put = await ac.put("/api/settings/ai-report",
                               json={"model": "gemini/x", "prompt": "지시", "enabled": True})
            get = await ac.get("/api/settings/ai-report")
    assert put.status_code == 200
    body = get.json()
    assert body["model"] == "gemini/x" and body["prompt"] == "지시" and body["enabled"] is True
```
(파일에 `import pytest`가 없으면 추가.)

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_settings_ai.py::test_get_put_ai_report_settings -v`
Expected: FAIL (404)

- [ ] **Step 3: 구현**

`app/routers/settings.py`의 `put_ai` 아래, 제너릭 `/{category}/{key}` 라우트 **위**에 추가:
```python
_AI_REPORT = "ai_report"


class AiReportIn(BaseModel):
    model: str | None = None
    prompt: str | None = None
    enabled: bool | None = None


@router.get("/ai-report")
async def get_ai_report(db: AsyncSession = Depends(get_db)):
    return {
        "model": await get_setting(db, _AI_REPORT, "model") or "",
        "prompt": await get_setting(db, _AI_REPORT, "prompt") or "",
        "enabled": (await get_setting(db, _AI_REPORT, "enabled") or "false").lower() == "true",
    }


@router.put("/ai-report")
async def put_ai_report(body: AiReportIn, db: AsyncSession = Depends(get_db)):
    if body.model is not None:
        await set_setting(db, _AI_REPORT, "model", body.model, is_secret=False)
    if body.prompt is not None:
        await set_setting(db, _AI_REPORT, "prompt", body.prompt, is_secret=False)
    if body.enabled is not None:
        await set_setting(db, _AI_REPORT, "enabled", "true" if body.enabled else "false", is_secret=False)
    return {"status": "ok"}
```

> 모델 목록은 기존 `/api/settings/ai/models`(ai_gateway 연결 사용)를 그대로 재사용한다 — 연결이 공유되므로 리포트 모델 선택에도 동일 목록이 맞다.

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_settings_ai.py -v`
Expected: PASS

- [ ] **Step 5: 전체 백엔드 회귀 실행**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q`
Expected: 기존 177 + 신규(약 25) 전부 PASS, 실패 0

- [ ] **Step 6: 커밋**
```bash
git add app/routers/settings.py tests/test_settings_ai.py
git commit -m "feat(report): /api/settings/ai-report 모델·프롬프트·토글"
```

---

## Task 11: 프론트엔드 — 리포트 페이지 + 메뉴 + 설정 섹션

**Files:**
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/pages/Reports.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: api.ts에 리포트 엔드포인트 추가**

`frontend/src/api.ts`의 `api` 객체 안에 추가(다른 메서드들 옆):
```typescript
  listReports: () => j<ReportRow[]>("/api/reports"),
  getReport: (id: number) => j<ReportRow>(`/api/reports/${id}`),
  createReport: () => j<ReportRow>("/api/reports", { method: "POST" }),
  deleteReport: (id: number) => j(`/api/reports/${id}`, { method: "DELETE" }),
  sendReportTelegram: (id: number) => j<{ sent: number }>(`/api/reports/${id}/send-telegram`, { method: "POST" }),
  getAiReport: () => j<{ model: string; prompt: string; enabled: boolean }>("/api/settings/ai-report"),
  saveAiReport: (a: { model?: string; prompt?: string; enabled?: boolean }) =>
    j("/api/settings/ai-report", { method: "PUT", body: JSON.stringify(a) }),
  getReportSchedule: () =>
    j<{ send_time: string; days_of_week: number[]; enabled: boolean } | null>("/api/reports/schedule"),
  saveReportSchedule: (s: { send_time: string; days_of_week: number[]; enabled: boolean }) =>
    j("/api/reports/schedule", { method: "PUT", body: JSON.stringify(s) }),
```
그리고 타입 선언(파일 내 다른 타입 선언부 또는 상단)에 추가:
```typescript
export type ReportRow = {
  id: number; title: string; content_md: string;
  model: string; trigger: string; created_at: string | null;
};
```

- [ ] **Step 2: Reports.tsx 작성**

`frontend/src/pages/Reports.tsx`:
```tsx
import { useEffect, useState } from "react";
import { api, ReportRow } from "../api";

export default function Reports() {
  const [rows, setRows] = useState<ReportRow[]>([]);
  const [selected, setSelected] = useState<ReportRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const load = async () => {
    try { setRows(await api.listReports()); }
    catch (e) { setError(String(e)); }
  };
  useEffect(() => { load(); }, []);

  const generate = async () => {
    setLoading(true); setError(""); setMsg("");
    try {
      const r = await api.createReport();
      await load();
      setSelected(r);
    } catch (e) {
      const s = String(e);
      setError(s.includes("409") ? "설정에서 AI 리포트를 활성화하고 게이트웨이·모델을 입력하세요." : s);
    } finally { setLoading(false); }
  };

  const remove = async (id: number) => {
    await api.deleteReport(id);
    if (selected?.id === id) setSelected(null);
    await load();
  };

  const send = async (id: number) => {
    setMsg(""); setError("");
    try { const r = await api.sendReportTelegram(id); setMsg(`텔레그램 발송 완료 (${r.sent}건)`); }
    catch (e) { setError(String(e).includes("409") ? "텔레그램이 설정되지 않았습니다." : String(e)); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">AI 리포트</h1>
        <button className="btn btn-primary" onClick={generate} disabled={loading}>
          {loading ? "생성 중…" : "리포트 생성"}
        </button>
      </div>
      {error && <div className="card text-sm" style={{ color: "var(--down)" }}>{error}</div>}
      {msg && <div className="card text-sm">{msg}</div>}

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        <div className="card space-y-1">
          {rows.length === 0 && <p className="text-sm text-muted">아직 생성된 리포트가 없습니다.</p>}
          {rows.map((r) => (
            <div key={r.id}
                 className={`flex items-center justify-between rounded px-2 py-1 cursor-pointer ${selected?.id === r.id ? "badge" : ""}`}
                 onClick={() => setSelected(r)}>
              <div className="min-w-0">
                <div className="truncate text-sm">{r.title}</div>
                <div className="text-xs text-muted">
                  {r.created_at?.slice(0, 16).replace("T", " ")} · {r.trigger}
                </div>
              </div>
              <button className="btn btn-ghost text-xs" onClick={(e) => { e.stopPropagation(); remove(r.id); }}>삭제</button>
            </div>
          ))}
        </div>

        <div className="card">
          {selected ? (
            <>
              <div className="mb-2 flex items-center justify-between">
                <h2 className="font-semibold">{selected.title}</h2>
                <button className="btn text-sm" onClick={() => send(selected.id)}>텔레그램 발송</button>
              </div>
              <div className="whitespace-pre-wrap text-sm leading-relaxed">{selected.content_md}</div>
            </>
          ) : (
            <p className="text-sm text-muted">왼쪽에서 리포트를 선택하거나 새로 생성하세요.</p>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: App.tsx 라우트 추가**

`frontend/src/App.tsx`:
- import 추가: `import Reports from "./pages/Reports";`
- `<Routes>` 안에 추가: `<Route path="/reports" element={<Reports />} />`

- [ ] **Step 4: AppShell.tsx 메뉴 추가**

`frontend/src/components/AppShell.tsx`의 nav 배열에서 "알림"과 "설정" 사이에 추가:
```tsx
  { to: "/reports", label: "리포트" },
```

- [ ] **Step 5: Settings.tsx에 "AI 리포트" 섹션 추가**

`frontend/src/pages/Settings.tsx`에 기존 AI(차트) 섹션 패턴을 따라 새 섹션을 추가한다. 상태·로딩은 기존 섹션과 동일 구조로:
```tsx
// 상태 (컴포넌트 상단 다른 useState들 옆)
const [rpt, setRpt] = useState({ model: "", prompt: "", enabled: false });
const [rptSched, setRptSched] = useState({ send_time: "06:30", days_of_week: [0,1,2,3,4] as number[], enabled: false });

// 로딩 (기존 useEffect 로더 안에 추가)
api.getAiReport().then(setRpt).catch(() => {});
api.getReportSchedule().then((s) => { if (s) setRptSched(s); }).catch(() => {});

// 저장 핸들러
const saveReport = async () => { await api.saveAiReport(rpt); };
const saveReportSchedule = async () => { await api.saveReportSchedule(rptSched); };
```
그리고 JSX에 카드 섹션 추가(기존 AI 섹션 마크업을 복제·수정):
```tsx
<section className="card space-y-3">
  <h2 className="font-semibold">AI 리포트</h2>
  <p className="text-sm text-muted">게이트웨이 연결(주소/키)은 위 "AI 분석" 설정을 공유합니다. 여기서는 리포트 전용 모델·프롬프트·자동발송을 설정합니다.</p>
  <label className="block text-sm">모델
    <select className="input" value={rpt.model} onChange={(e) => setRpt({ ...rpt, model: e.target.value })}>
      <option value={rpt.model}>{rpt.model || "(모델 선택 — AI 분석 설정의 '모델 새로고침'으로 목록을 불러오세요)"}</option>
    </select>
  </label>
  <label className="block text-sm">프롬프트
    <textarea className="input h-32" value={rpt.prompt}
              placeholder="비워두면 기본 프롬프트 사용"
              onChange={(e) => setRpt({ ...rpt, prompt: e.target.value })} />
  </label>
  <label className="flex items-center gap-2 text-sm">
    <input type="checkbox" checked={rpt.enabled} onChange={(e) => setRpt({ ...rpt, enabled: e.target.checked })} />
    AI 리포트 활성화
  </label>
  <button className="btn btn-primary" onClick={saveReport}>리포트 설정 저장</button>

  <div className="border-t pt-3 space-y-2" style={{ borderColor: "var(--border)" }}>
    <h3 className="text-sm font-semibold">자동 발송 스케줄</h3>
    <label className="block text-sm">발송 시각(KST)
      <input className="input" type="time" value={rptSched.send_time}
             onChange={(e) => setRptSched({ ...rptSched, send_time: e.target.value })} />
    </label>
    <div className="flex flex-wrap gap-2 text-sm">
      {["월","화","수","목","금","토","일"].map((d, i) => (
        <label key={i} className="flex items-center gap-1">
          <input type="checkbox" checked={rptSched.days_of_week.includes(i)}
                 onChange={(e) => setRptSched({
                   ...rptSched,
                   days_of_week: e.target.checked
                     ? [...rptSched.days_of_week, i]
                     : rptSched.days_of_week.filter((x) => x !== i),
                 })} />
          {d}
        </label>
      ))}
    </div>
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={rptSched.enabled}
             onChange={(e) => setRptSched({ ...rptSched, enabled: e.target.checked })} />
      자동 발송 사용
    </label>
    <button className="btn btn-primary" onClick={saveReportSchedule}>스케줄 저장</button>
  </div>
</section>
```
> 모델 드롭다운은 단순화를 위해 현재 저장값만 표시한다. 모델 목록 새로고침은 기존 "AI 분석" 섹션의 버튼(같은 `/api/settings/ai/models`)으로 확인 후 값을 복사·입력하거나, 기존 섹션 모델 목록 상태를 공유해 옵션을 채워도 된다(선택 구현). 최소 동작은 위 코드로 충분하다.

- [ ] **Step 6: 빌드·타입체크**

Run: `cd frontend && npm run build`
Expected: 빌드 성공(타입 에러 0). 실패 시 타입 선언/시그니처 수정.

- [ ] **Step 7: 커밋**
```bash
git add frontend/src/api.ts frontend/src/pages/Reports.tsx frontend/src/App.tsx frontend/src/components/AppShell.tsx frontend/src/pages/Settings.tsx
git commit -m "feat(report): 리포트 페이지·메뉴·설정 섹션(프론트)"
```

---

## Task 12: 최종 검증 + 로드맵 반영

**Files:**
- Modify: `docs/superpowers/ROADMAP.md`

- [ ] **Step 1: 백엔드 전체 테스트**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q`
Expected: 전부 PASS, 실패 0.

- [ ] **Step 2: 프론트 빌드**

Run: `cd frontend && npm run build`
Expected: 성공.

- [ ] **Step 3: ROADMAP에 3단계 B 완료 항목 추가**

`docs/superpowers/ROADMAP.md`의 "### 3단계 B/C/D — 미착수" 섹션을 갱신: B를 별도 "구현 완료" 항목으로 옮기고 spec/plan 경로·테스트 수·"실게이트웨이/실텔레그램 스모크는 사용자 확인 대기"를 기록. C/D는 미착수로 유지.

- [ ] **Step 4: 커밋**
```bash
git add docs/superpowers/ROADMAP.md
git commit -m "docs(roadmap): 3단계 B AI 포트폴리오 리포트 완료 반영"
```

> **실 스모크(사용자 확인 대기)**: 설정에서 게이트웨이 연결·리포트 모델·활성화 입력 → 리포트 페이지 "리포트 생성" → 본문 표시 확인 → "텔레그램 발송" 확인 → 설정에서 스케줄 등록 후 자동 발송 확인. 게이트웨이/텔레그램 자격증명이 필요하므로 구현 단계에서 자동화하지 않는다.

---

## Self-Review (작성자 확인 완료)

- **스펙 커버리지**: 목적(진단+추세+제안)=Task6 DEFAULT_PROMPT 구조 / 트리거·전달(수동+스케줄+텔레그램)=Task8·9 / 이력저장=Task1·5 / 입력(린+종목수익률)=Task4 / 제안수위(비지시)=Task6 프롬프트+디스클레이머 / 신규메뉴=Task11 / 설정 분리(연결 공유, 모델·프롬프트·토글 전용)=Task6·10 / 공용 헬퍼 추출=Task3 / 에러처리=Task6·8·9. 모두 매핑됨.
- **플레이스홀더**: 없음(모든 코드 실내용).
- **타입 일관성**: `generate_text`/`collect_input_block`/`create_report(db, trigger)`/`report_store.create(db,title,content_md,model,trigger)`/`send_report(db, report)`/`ReportRow` 시그니처가 정의처와 호출처에서 일치.
