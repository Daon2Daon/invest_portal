# 보유/관심 IA + 자산 상세 허브 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 보유(포트폴리오)/관심종목을 파생 분류로 나누고, 자산별 기능(차트·AI분석·스케줄)을 자산 상세 허브(`/asset/:id`) 한 곳으로 모은다.

**Architecture:** 백엔드는 신규 테이블 없이 조회 엔드포인트 2개(`GET /api/watchlist`, `GET /api/assets/{id}/detail`)와 공유 헬퍼(`held_asset_ids`)만 추가. 프론트는 네비를 재편하고 관심종목 페이지를 신설하며 `Charts.tsx`를 `AssetDetail.tsx` 허브로 일반화한다.

**Tech Stack:** FastAPI + async SQLAlchemy 2.0(asyncpg, PostgreSQL), pytest/pytest-asyncio + httpx ASGITransport, React 19 + react-router-dom v7 + Tailwind + Vite/TypeScript.

설계 spec: `docs/superpowers/specs/2026-06-18-holding-watchlist-ia-design.md`

---

## 파일 구조

신규
- `app/services/portfolio/watchlist_service.py` — 관심종목 목록 조회
- `app/routers/watchlist.py` — `GET /api/watchlist`
- `frontend/src/pages/Watchlist.tsx` — 관심종목 페이지
- `frontend/src/pages/AssetDetail.tsx` — 자산 상세 허브
- `tests/test_watchlist.py`, `tests/test_assets_detail.py`

수정
- `app/services/portfolio/portfolio_service.py` — `held_asset_ids`, `get_asset_detail` 추가
- `app/routers/assets.py` — `GET /api/assets/{id}/detail` 추가
- `app/main.py` — watchlist 라우터 등록
- `frontend/src/App.tsx` — 라우트/네비 재편
- `frontend/src/api.ts` — 함수·타입 추가
- `frontend/src/pages/Dashboard.tsx` — 종목 행 클릭 → 상세 이동

삭제
- `frontend/src/pages/Charts.tsx` (→ `AssetDetail.tsx`로 대체)

> 백엔드 통합 테스트는 `tests/conftest.py`의 `db_session` 픽스처를 쓰며 `TEST_DATABASE_URL` 미설정 시 자동 skip된다. 실행 전 해당 환경변수가 설정돼 있어야 실제로 검증된다.

---

### Task 1: `held_asset_ids` 공유 헬퍼

**Files:**
- Modify: `app/services/portfolio/portfolio_service.py`
- Test: `tests/test_watchlist.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_watchlist.py` 생성:

```python
import pytest
from unittest.mock import patch, AsyncMock

from app.models import Asset, Holding
from app.services.market.types import Quote
from app.services.portfolio.portfolio_service import held_asset_ids
from app.services.portfolio.watchlist_service import get_watchlist


def _asset(**kw):
    base = dict(ticker="T", name="N", asset_type="stock", market="US",
                currency="USD", data_source="yfinance", fetch_symbol="T")
    base.update(kw)
    return Asset(**base)


@pytest.mark.asyncio
async def test_held_asset_ids(db_session):
    a1 = _asset(ticker="AAA", fetch_symbol="AAA")
    a2 = _asset(ticker="BBB", fetch_symbol="BBB")
    db_session.add_all([a1, a2])
    await db_session.commit()
    db_session.add(Holding(asset_id=a1.asset_id, quantity=1, purchase_price=10, fee=0))
    await db_session.commit()
    ids = await held_asset_ids(db_session)
    assert a1.asset_id in ids
    assert a2.asset_id not in ids
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_watchlist.py::test_held_asset_ids -v`
Expected: FAIL — `ImportError: cannot import name 'held_asset_ids'` (또는 `watchlist_service` 미존재). 이 시점에는 `get_watchlist` import도 실패하므로 Task 2 후 함께 통과한다.

- [ ] **Step 3: 최소 구현**

`app/services/portfolio/portfolio_service.py` 파일 상단의 import 블록(`from sqlalchemy import select` 등이 있는 부분)은 그대로 두고, `aggregate_position`/`build_allocation` 아래, `get_portfolio` 위(또는 파일 끝 import 블록 근처)에 추가:

```python
async def held_asset_ids(db: AsyncSession) -> set[int]:
    """holding lot 행이 1개 이상 존재하는 asset_id 집합(보유 판정용)."""
    rows = await db.execute(select(Holding.asset_id).distinct())
    return set(rows.scalars().all())
```

> `select`, `AsyncSession`, `Holding`은 이 파일에 이미 import되어 있다(43~46행). 추가 import 불필요.

- [ ] **Step 4: (Task 2 완료 후 함께) 테스트 통과 확인**

Run: `pytest tests/test_watchlist.py::test_held_asset_ids -v`
Expected: PASS (TEST_DATABASE_URL 미설정 시 SKIP)

- [ ] **Step 5: 커밋** (Task 2와 함께 커밋 — 같은 테스트 파일을 공유하므로)

---

### Task 2: `watchlist_service.get_watchlist`

**Files:**
- Create: `app/services/portfolio/watchlist_service.py`
- Test: `tests/test_watchlist.py` (Task 1에서 생성)

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_watchlist.py` 끝에 추가:

```python
@pytest.mark.asyncio
async def test_get_watchlist_excludes_held(db_session):
    held = _asset(ticker="AAA", fetch_symbol="AAA")
    watch = _asset(ticker="BBB", fetch_symbol="BBB")
    db_session.add_all([held, watch])
    await db_session.commit()
    db_session.add(Holding(asset_id=held.asset_id, quantity=1, purchase_price=10, fee=0))
    await db_session.commit()
    q = Quote(price=100.0, currency="USD", change=2.0, change_pct=2.0, status="ok")
    with patch("app.services.portfolio.watchlist_service.get_quote", AsyncMock(return_value=q)):
        rows = await get_watchlist(db_session)
    assert {r["ticker"] for r in rows} == {"BBB"}
    assert rows[0]["current_price"] == 100.0
    assert rows[0]["change_pct"] == 2.0


@pytest.mark.asyncio
async def test_get_watchlist_error_quote_sets_price_none(db_session):
    a = _asset(ticker="CCC", fetch_symbol="CCC")
    db_session.add(a)
    await db_session.commit()
    q = Quote(price=0.0, currency="USD", status="error")
    with patch("app.services.portfolio.watchlist_service.get_quote", AsyncMock(return_value=q)):
        rows = await get_watchlist(db_session)
    assert rows[0]["current_price"] is None
    assert rows[0]["price_status"] == "error"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_watchlist.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.portfolio.watchlist_service`

- [ ] **Step 3: 최소 구현**

`app/services/portfolio/watchlist_service.py` 생성:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset
from app.services.market.quote_service import get_quote
from app.services.portfolio.portfolio_service import held_asset_ids


async def get_watchlist(db: AsyncSession) -> list[dict]:
    """관심종목(보유 lot 없는 활성 자산) + 라이브 시세 목록.
    시세 조회 실패(status!=ok) 시 current_price는 None으로 두되 목록에는 유지한다."""
    held = await held_asset_ids(db)
    assets = (await db.execute(
        select(Asset).where(Asset.is_active == True)  # noqa: E712
    )).scalars().all()
    out: list[dict] = []
    for a in assets:
        if a.asset_id in held:
            continue
        q = await get_quote(a)
        out.append({
            "asset_id": a.asset_id, "ticker": a.ticker, "name": a.name,
            "market": a.market, "currency": a.currency, "asset_type": a.asset_type,
            "asset_class": a.asset_class,
            "current_price": q.price if q.status == "ok" else None,
            "change": q.change, "change_pct": q.change_pct, "price_status": q.status,
        })
    return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_watchlist.py -v`
Expected: PASS (3개 — held_asset_ids 포함) 또는 SKIP

- [ ] **Step 5: 커밋**

```bash
git add app/services/portfolio/portfolio_service.py app/services/portfolio/watchlist_service.py tests/test_watchlist.py
git commit -m "feat(ia): held_asset_ids 헬퍼 + 관심종목 조회 서비스"
```

---

### Task 3: `GET /api/watchlist` 라우터 + 등록

**Files:**
- Create: `app/routers/watchlist.py`
- Modify: `app/main.py:12`, `app/main.py:37`
- Test: `tests/test_watchlist.py`

- [ ] **Step 1: 실패하는 API 테스트 추가**

`tests/test_watchlist.py` 끝에 추가:

```python
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_watchlist_endpoint_returns_rows():
    rows = [{"asset_id": 5, "ticker": "BBB", "name": "B", "market": "US",
             "currency": "USD", "asset_type": "stock", "asset_class": None,
             "current_price": 100.0, "change": 1.0, "change_pct": 1.0, "price_status": "ok"}]
    with patch("app.routers.watchlist.get_watchlist", AsyncMock(return_value=rows)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            resp = await ac.get("/api/watchlist")
    assert resp.status_code == 200
    assert resp.json()[0]["ticker"] == "BBB"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_watchlist.py::test_watchlist_endpoint_returns_rows -v`
Expected: FAIL — 404 (라우터 미등록) 또는 patch 대상(`app.routers.watchlist`) 미존재 ModuleNotFoundError

- [ ] **Step 3: 라우터 생성 + 등록**

`app/routers/watchlist.py` 생성:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.portfolio.watchlist_service import get_watchlist

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("")
async def watchlist(db: AsyncSession = Depends(get_db)):
    return await get_watchlist(db)
```

`app/main.py` 12행 import에 `watchlist` 추가:

```python
from app.routers import assets, holdings, portfolio, fx, settings as settings_router, cash, charts, watchlist
```

`app/main.py` 37행 include 루프에 `watchlist.router` 추가:

```python
for r in (assets.router, holdings.router, portfolio.router, fx.router, settings_router.router, cash.router, charts.router, watchlist.router):
    app.include_router(r)
```

> SPA 폴백(`app/main.py:67`)은 `/api`로 시작하는 경로를 먼저 404 처리에서 제외하므로 `/api/watchlist`가 라우터로 정상 도달한다. 추가 조치 불필요.

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_watchlist.py::test_watchlist_endpoint_returns_rows -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add app/routers/watchlist.py app/main.py tests/test_watchlist.py
git commit -m "feat(ia): GET /api/watchlist 라우터 등록"
```

---

### Task 4: `get_asset_detail` + `GET /api/assets/{id}/detail`

**Files:**
- Modify: `app/services/portfolio/portfolio_service.py`
- Modify: `app/routers/assets.py`
- Test: `tests/test_assets_detail.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_assets_detail.py` 생성:

```python
import pytest
from unittest.mock import patch, AsyncMock

from app.models import Asset, Holding
from app.services.market.types import Quote
from app.services.portfolio.portfolio_service import get_asset_detail


def _asset(**kw):
    base = dict(ticker="T", name="N", asset_type="stock", market="US",
                currency="USD", data_source="yfinance", fetch_symbol="T")
    base.update(kw)
    return Asset(**base)


@pytest.mark.asyncio
async def test_detail_none_when_missing(db_session):
    assert await get_asset_detail(db_session, 999999) is None


@pytest.mark.asyncio
async def test_detail_watchlist_no_holding(db_session):
    a = _asset(ticker="AAA", fetch_symbol="AAA")
    db_session.add(a)
    await db_session.commit()
    q = Quote(price=100.0, currency="USD", change_pct=1.0, status="ok")
    with patch("app.services.portfolio.portfolio_service.get_quote", AsyncMock(return_value=q)):
        d = await get_asset_detail(db_session, a.asset_id)
    assert d["held"] is False
    assert d["holding_summary"] is None
    assert d["quote"]["price"] == 100.0
    assert d["asset"]["ticker"] == "AAA"


@pytest.mark.asyncio
async def test_detail_held_has_summary(db_session):
    a = _asset(ticker="BBB", fetch_symbol="BBB")
    db_session.add(a)
    await db_session.commit()
    db_session.add(Holding(asset_id=a.asset_id, quantity=10, purchase_price=90, fee=0))
    await db_session.commit()
    q = Quote(price=100.0, currency="USD", status="ok")
    with patch("app.services.portfolio.portfolio_service.get_quote", AsyncMock(return_value=q)), \
         patch("app.services.portfolio.portfolio_service.get_rate_to_krw", AsyncMock(return_value=1300.0)):
        d = await get_asset_detail(db_session, a.asset_id)
    assert d["held"] is True
    assert d["holding_summary"]["quantity"] == 10
    assert d["holding_summary"]["avg_price"] == 90
    assert d["holding_summary"]["value_krw"] == 10 * 100 * 1300.0
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_assets_detail.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_asset_detail'`

- [ ] **Step 3: `get_asset_detail` 구현**

`app/services/portfolio/portfolio_service.py` 상단 import 블록(43~47행)에 `AssetOut` import 추가:

```python
from app.schemas.asset import AssetOut
```

`get_portfolio` 함수 아래에 추가:

```python
async def get_asset_detail(db: AsyncSession, asset_id: int) -> dict | None:
    """자산 상세 허브 헤더용 집계. 보유/관심 공통. 없으면 None."""
    asset = await db.get(Asset, asset_id)
    if asset is None:
        return None
    quote = await get_quote(asset)
    lots = (await db.execute(
        select(Holding).where(Holding.asset_id == asset_id)
    )).scalars().all()
    summary = None
    if lots:
        fx_now = await get_rate_to_krw(db, asset.currency) or 0.0
        lot_dicts = [dict(quantity=float(l.quantity), purchase_price=float(l.purchase_price),
                          fee=float(l.fee or 0)) for l in lots]
        agg = aggregate_position(lot_dicts, current_price=quote.price, fx_now=fx_now)
        summary = {"quantity": agg["quantity"], "avg_price": agg["avg_price"],
                   "value_krw": agg["value_krw"], "profit_loss_krw": agg["profit_loss_krw"],
                   "profit_loss_pct": agg["profit_loss_pct"]}
    return {
        "asset": AssetOut.model_validate(asset).model_dump(),
        "held": bool(lots),
        "holding_summary": summary,
        "quote": {"price": quote.price, "currency": quote.currency, "change": quote.change,
                  "change_pct": quote.change_pct, "status": quote.status},
    }
```

> `Asset`, `Holding`, `select`, `get_quote`, `get_rate_to_krw`, `aggregate_position`은 이 파일에 이미 존재/ import 되어 있다(43~47행 + 모듈 상단 함수). `AssetOut`만 신규 import.

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_assets_detail.py -v`
Expected: PASS (3개) 또는 SKIP

- [ ] **Step 5: 라우터 엔드포인트 추가**

`app/routers/assets.py` 상단 import에 추가:

```python
from app.services.portfolio.portfolio_service import get_asset_detail
```

`asset_quote` 라우트(62행) 아래에 추가:

```python
@router.get("/{asset_id}/detail")
async def asset_detail(asset_id: int, db: AsyncSession = Depends(get_db)):
    d = await get_asset_detail(db, asset_id)
    if d is None:
        raise HTTPException(404, "asset not found")
    return d
```

- [ ] **Step 6: 라우트 동작 확인(이미 import된 의존성으로 충돌 없음 검증)**

Run: `pytest tests/test_assets_detail.py -v && python -c "import app.main"`
Expected: 테스트 PASS/SKIP, import 에러 없음

- [ ] **Step 7: 커밋**

```bash
git add app/services/portfolio/portfolio_service.py app/routers/assets.py tests/test_assets_detail.py
git commit -m "feat(ia): GET /api/assets/{id}/detail (보유 요약 포함)"
```

---

### Task 5: 프론트 `api.ts` 함수·타입 추가

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: api 객체에 함수 추가**

`frontend/src/api.ts`의 `export const api = { ... }` 객체 안(마지막 `deleteSchedule` 뒤, 닫는 `}` 앞)에 추가:

```ts
  listWatchlist: () => j<WatchlistItem[]>("/api/watchlist"),
  createWatchlistAsset: (a: any) => j("/api/assets", { method: "POST", body: JSON.stringify(a) }),
  assetDetail: (id: number) => j<AssetDetailOut>(`/api/assets/${id}/detail`),
  deleteAsset: (id: number) => j(`/api/assets/${id}`, { method: "DELETE" }),
```

- [ ] **Step 2: 타입 인터페이스 추가**

`frontend/src/api.ts` 파일 끝(마지막 인터페이스 뒤)에 추가:

```ts
export interface WatchlistItem {
  asset_id: number; ticker: string; name: string; market: string; currency: string;
  asset_type: string; asset_class: string | null;
  current_price: number | null; change: number | null; change_pct: number | null;
  price_status: string;
}
export interface HoldingSummary {
  quantity: number; avg_price: number; value_krw: number;
  profit_loss_krw: number; profit_loss_pct: number;
}
export interface AssetDetailOut {
  asset: {
    asset_id: number; ticker: string; name: string; market: string; currency: string;
    asset_type: string; asset_class: string | null; data_source: string;
  };
  held: boolean;
  holding_summary: HoldingSummary | null;
  quote: { price: number; currency: string; change: number | null; change_pct: number | null; status: string };
}
```

- [ ] **Step 3: 타입 체크**

Run: `cd frontend && npx tsc --noEmit`
Expected: 에러 없음 (WatchlistItem/AssetDetailOut 미사용 경고는 tsc noEmit에서 발생하지 않음 — 사용처는 후속 Task에서 추가)

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/api.ts
git commit -m "feat(ia): api.ts 관심종목/자산상세 클라이언트 추가"
```

---

### Task 6: 관심종목 페이지 `Watchlist.tsx`

**Files:**
- Create: `frontend/src/pages/Watchlist.tsx`

- [ ] **Step 1: 페이지 작성**

`frontend/src/pages/Watchlist.tsx` 생성:

```tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { WatchlistItem, ResolveResponse } from "../api";

const MARKETS = ["US", "KR", "JP", "CRYPTO"];
const ASSET_TYPES = [
  { code: "", label: "자동 감지" }, { code: "stock", label: "주식" },
  { code: "etf", label: "ETF" }, { code: "bond", label: "채권 (수동가격)" },
  { code: "commodity", label: "원자재" }, { code: "crypto", label: "가상자산" },
];
const inp = "border rounded px-2 py-1";

export default function Watchlist() {
  const nav = useNavigate();
  const [rows, setRows] = useState<WatchlistItem[]>([]);
  const [ticker, setTicker] = useState(""); const [market, setMarket] = useState("US");
  const [assetType, setAssetType] = useState("");
  const [preview, setPreview] = useState<ResolveResponse | null>(null);
  const [msg, setMsg] = useState("");

  const load = async () => setRows(await api.listWatchlist());
  useEffect(() => { load(); }, []);

  const doResolve = async () => {
    setMsg("");
    setPreview(await api.resolve(ticker, market, assetType || undefined));
  };
  const addWatch = async () => {
    if (!preview?.asset) return;
    try {
      await api.createWatchlistAsset(preview.asset);
      setPreview(null); setTicker(""); setMsg("추가됨");
      await load();
    } catch (e: any) { setMsg("추가 실패: " + e.message); }
  };
  const remove = async (id: number) => {
    if (!confirm("이 관심종목을 삭제할까요?")) return;
    await api.deleteAsset(id); await load();
  };

  const pct = (n: number | null) =>
    n == null ? "—" : <span className={n >= 0 ? "text-red-600" : "text-blue-600"}>{n >= 0 ? "+" : ""}{n.toFixed(2)}%</span>;

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold">관심종목</h1>

      <section className="space-y-2">
        <h2 className="font-semibold text-gray-700">관심종목 추가</h2>
        <div className="flex gap-2 items-center flex-wrap">
          <input className={inp} placeholder="티커 (AAPL, 005930, BTC, GC=F)"
            value={ticker} onChange={(e) => setTicker(e.target.value)} />
          <select className={inp} value={market} onChange={(e) => setMarket(e.target.value)}>
            {MARKETS.map((m) => <option key={m}>{m}</option>)}
          </select>
          <select className={inp} value={assetType} onChange={(e) => setAssetType(e.target.value)}>
            {ASSET_TYPES.map((t) => <option key={t.code} value={t.code}>{t.label}</option>)}
          </select>
          <button onClick={doResolve} className="px-3 py-1 rounded bg-gray-800 text-white">조회</button>
          {msg && <span className="text-sm text-gray-600">{msg}</span>}
        </div>
        {preview && (preview.ok && preview.asset ? (
          <div className="rounded border p-3 bg-green-50 flex items-center gap-3 flex-wrap">
            <div><b>{preview.asset.name}</b> · {preview.asset.currency} · {preview.asset.asset_type} · 현재가 {preview.asset.current_price ?? "—"}</div>
            <button onClick={addWatch} className="px-3 py-1 rounded bg-blue-600 text-white">관심 추가</button>
          </div>
        ) : (
          <div className="rounded border p-3 bg-amber-50">
            <div>조회 실패 (시도: {preview.tried.join(", ")})</div>
            <div className="text-sm text-gray-600">{preview.suggestion}</div>
          </div>
        ))}
      </section>

      <table className="w-full text-sm border-collapse">
        <thead><tr className="border-b text-left text-gray-500">
          <th className="py-2">종목</th><th>현재가</th><th>변화</th><th>자산군</th><th></th>
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.asset_id} className="border-b hover:bg-gray-50 cursor-pointer"
              onClick={() => nav(`/asset/${r.asset_id}`)}>
              <td className="py-2">{r.name} <span className="text-gray-400">{r.ticker}·{r.market}</span></td>
              <td>{r.current_price == null
                ? <span className="text-amber-600">⚠{r.price_status}</span>
                : r.current_price.toLocaleString()}</td>
              <td>{pct(r.change_pct)}</td>
              <td>{r.asset_class ?? "—"}</td>
              <td className="whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                <button onClick={() => remove(r.asset_id)} className="text-red-600">삭제</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: 타입 체크**

Run: `cd frontend && npx tsc --noEmit`
Expected: 에러 없음 (App.tsx에서 아직 라우팅 안 했으므로 미사용이지만 tsc noEmit은 unused import만 경고하지 않음 → Task 7에서 연결)

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/pages/Watchlist.tsx
git commit -m "feat(ia): 관심종목 페이지"
```

---

### Task 7: 자산 상세 허브 `AssetDetail.tsx` + Charts.tsx 제거

**Files:**
- Create: `frontend/src/pages/AssetDetail.tsx`
- Delete: `frontend/src/pages/Charts.tsx`

- [ ] **Step 1: AssetDetail 작성** (Charts.tsx 기능을 라우트 파라미터 기반 + 헤더 추가로 일반화)

`frontend/src/pages/AssetDetail.tsx` 생성:

```tsx
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import type { AssetDetailOut } from "../api";

const krw = (n: number) => n.toLocaleString("ko-KR", { maximumFractionDigits: 0 });
const DAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"];

export default function AssetDetail() {
  const { id } = useParams();
  const assetId = id ? Number(id) : null;

  const [detail, setDetail] = useState<AssetDetailOut | null>(null);
  const [nonce, setNonce] = useState(() => Date.now());
  const [msg, setMsg] = useState("");
  const [analysis, setAnalysis] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [schedTime, setSchedTime] = useState("08:30");
  const [schedDays, setSchedDays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [schedEnabled, setSchedEnabled] = useState(false);
  const [schedMsg, setSchedMsg] = useState("");

  useEffect(() => {
    if (!assetId) return;
    api.assetDetail(assetId).then(setDetail).catch(() => setDetail(null));
    api.getSchedule(assetId).then((s) => {
      if (s) { setSchedTime(s.send_time); setSchedDays(s.days_of_week); setSchedEnabled(s.enabled); }
      else { setSchedTime("08:30"); setSchedDays([0, 1, 2, 3, 4]); setSchedEnabled(false); }
      setSchedMsg("");
    });
  }, [assetId]);

  const send = async () => {
    if (!assetId) return;
    setMsg("발송 중…");
    try {
      const r: any = await api.sendChartTelegram(assetId);
      const extra = r.analysis_sent ? " + AI 분석" : "";
      setMsg(r.ok ? `텔레그램 발송 완료 (${r.sent}장${extra})` : "발송 실패");
    } catch (e: any) { setMsg("발송 실패: " + e.message); }
  };
  const analyze = async () => {
    if (!assetId) return;
    setAnalyzing(true); setAnalysis(""); setMsg("");
    try { setAnalysis((await api.analyzeChart(assetId)).analysis); }
    catch (e: any) { setAnalysis("분석 실패: " + e.message); }
    finally { setAnalyzing(false); }
  };
  const toggleDay = (d: number) =>
    setSchedDays((prev) => prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort());
  const saveSched = async () => {
    if (!assetId) return;
    setSchedMsg("저장 중…");
    try { await api.saveSchedule(assetId, { send_time: schedTime, days_of_week: schedDays, enabled: schedEnabled }); setSchedMsg("저장됨"); }
    catch (e: any) { setSchedMsg("저장 실패: " + e.message); }
  };
  const deleteSched = async () => {
    if (!assetId) return;
    setSchedMsg("삭제 중…");
    try { await api.deleteSchedule(assetId); setSchedEnabled(false); setSchedMsg("삭제됨"); }
    catch (e: any) { setSchedMsg("삭제 실패: " + e.message); }
  };
  const src = (period: "daily" | "weekly") =>
    assetId ? `${api.chartUrl(assetId, period)}&n=${nonce}` : "";

  if (!assetId) return <div className="p-6">잘못된 경로입니다.</div>;

  const a = detail?.asset;
  const q = detail?.quote;
  const hs = detail?.holding_summary;

  return (
    <div className="p-6 space-y-4">
      {a && (
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-xl font-bold">{a.name} <span className="text-gray-400 text-base">{a.ticker}·{a.market}</span></h1>
          <span className={`px-2 py-0.5 rounded text-xs ${detail!.held ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-600"}`}>
            {detail!.held ? "보유" : "관심"}
          </span>
          {q && q.status === "ok" && (
            <span className="text-lg">
              {q.price.toLocaleString()} {a.currency}
              {q.change_pct != null && (
                <span className={`ml-2 text-sm ${q.change_pct >= 0 ? "text-red-600" : "text-blue-600"}`}>
                  {q.change_pct >= 0 ? "+" : ""}{q.change_pct.toFixed(2)}%
                </span>
              )}
            </span>
          )}
        </div>
      )}
      {hs && (
        <div className="text-sm text-gray-700">
          수량 {hs.quantity} · 평단 {hs.avg_price.toLocaleString()} · 평가손익 <span className={hs.profit_loss_krw >= 0 ? "text-red-600" : "text-blue-600"}>₩{krw(hs.profit_loss_krw)} ({hs.profit_loss_pct.toFixed(1)}%)</span>
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        <button onClick={() => setNonce((n) => n + 1)} className="px-3 py-1 rounded bg-gray-800 text-white">새로고침</button>
        <button onClick={analyze} disabled={analyzing} className="px-3 py-1 rounded bg-emerald-600 text-white disabled:opacity-50">
          {analyzing ? "분석 중…" : "AI 분석"}
        </button>
        <button onClick={send} className="px-3 py-1 rounded bg-blue-600 text-white">텔레그램 발송</button>
        {msg && <span className="text-sm text-gray-600">{msg}</span>}
      </div>

      {analysis && (
        <div className="border rounded p-3 bg-gray-50 whitespace-pre-wrap text-sm leading-relaxed max-w-3xl">{analysis}</div>
      )}

      <div className="border rounded p-3 bg-white max-w-3xl space-y-2">
        <h2 className="font-semibold text-gray-700">자동 발송 스케줄</h2>
        <div className="flex items-center gap-2 flex-wrap">
          <label className="text-sm">발송 시각</label>
          <input type="time" className="border rounded px-2 py-1" value={schedTime} onChange={(e) => setSchedTime(e.target.value)} />
          <span className="text-xs text-gray-500">(KST)</span>
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          {DAY_LABELS.map((lbl, d) => (
            <button key={d} type="button" onClick={() => toggleDay(d)}
              className={`px-2 py-1 rounded text-sm border ${schedDays.includes(d) ? "bg-blue-600 text-white" : "bg-gray-100"}`}>{lbl}</button>
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

      <div className="space-y-6">
        <div>
          <h2 className="font-semibold mb-1">일봉</h2>
          <img src={src("daily")} alt="daily chart" className="max-w-full border rounded"
            onError={(e) => ((e.target as HTMLImageElement).alt = "차트를 가져올 수 없습니다(수동/이력없음 자산일 수 있음)")} />
        </div>
        <div>
          <h2 className="font-semibold mb-1">주봉</h2>
          <img src={src("weekly")} alt="weekly chart" className="max-w-full border rounded"
            onError={(e) => ((e.target as HTMLImageElement).alt = "차트를 가져올 수 없습니다(수동/이력없음 자산일 수 있음)")} />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Charts.tsx 삭제**

```bash
git rm frontend/src/pages/Charts.tsx
```

- [ ] **Step 3: 타입 체크**

Run: `cd frontend && npx tsc --noEmit`
Expected: 에러 없음. (App.tsx가 아직 Charts를 import하면 에러 — Task 8에서 교체. 이 Task만 단독 검증 시 App.tsx의 Charts import을 임시로 두면 tsc가 "Cannot find module './pages/Charts'" 에러를 낸다.)

> 주의: Step 2 삭제로 App.tsx의 `import Charts`가 깨지므로, **Task 8과 연속 실행**하거나 Step 4 커밋을 Task 8 커밋과 합친다. 단독 커밋하려면 Task 8을 먼저 끝내고 함께 커밋할 것.

- [ ] **Step 4: 커밋** (Task 8과 함께)

---

### Task 8: 네비/라우트 재편 + 대시보드 행 클릭

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: App.tsx 전체 교체**

`frontend/src/App.tsx`:

```tsx
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Holdings from "./pages/Holdings";
import Watchlist from "./pages/Watchlist";
import AssetDetail from "./pages/AssetDetail";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <BrowserRouter>
      <nav className="flex gap-4 border-b px-6 py-3">
        <Link to="/" className="font-semibold">포트폴리오</Link>
        <Link to="/watchlist">관심종목</Link>
        <Link to="/manage">관리</Link>
        <Link to="/settings">설정</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/watchlist" element={<Watchlist />} />
        <Route path="/manage" element={<Holdings />} />
        <Route path="/asset/:id" element={<AssetDetail />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </BrowserRouter>
  );
}
```

- [ ] **Step 2: Dashboard 종목 행 클릭 → 상세 이동**

`frontend/src/pages/Dashboard.tsx` 1행 import 수정:

```tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { PortfolioOut } from "../api";
```

`export default function Dashboard() {` 바로 다음 줄에 추가:

```tsx
  const nav = useNavigate();
```

포지션 테이블의 행(`{data.positions.map((p) => (` 안의 `<tr ...>`)을 다음으로 교체:

```tsx
            <tr key={p.asset_id} className="border-b hover:bg-gray-50 cursor-pointer"
              onClick={() => nav(`/asset/${p.asset_id}`)}>
```

- [ ] **Step 3: 타입 체크 + 빌드**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: tsc 에러 없음, vite 빌드 성공(`dist/` 생성)

- [ ] **Step 4: 커밋** (Task 7 + Task 8 합산)

```bash
git add frontend/src/App.tsx frontend/src/pages/Dashboard.tsx frontend/src/pages/AssetDetail.tsx
git rm --cached frontend/src/pages/Charts.tsx 2>/dev/null; true
git commit -m "feat(ia): 자산 상세 허브 + 네비 재편(포트폴리오/관심종목/관리), 차트 페이지 흡수"
```

---

### Task 9: 전체 검증 + 수동 스모크

**Files:** 없음(검증만)

- [ ] **Step 1: 백엔드 전체 테스트**

Run: `pytest -q`
Expected: 신규 테스트 PASS(또는 TEST_DATABASE_URL 미설정 시 watchlist/detail 통합 테스트 SKIP), 기존 테스트 회귀 없음

- [ ] **Step 2: 앱 import/부팅 스모크**

Run: `python -c "import app.main"`
Expected: 에러 없음(라우터 등록·import 정합)

- [ ] **Step 3: 프론트 빌드**

Run: `cd frontend && npm run build`
Expected: 빌드 성공

- [ ] **Step 4: 수동 스모크(앱 실행 후 브라우저)**

확인 항목:
- 네비: 포트폴리오 / 관심종목 / 관리 / 설정 노출, "차트" 메뉴 없음
- 포트폴리오 종목 행 클릭 → `/asset/:id` 진입, 헤더에 "보유" 뱃지 + 수량/평단/평가손익 표시
- 관심종목 페이지: 티커 조회 → "관심 추가" → 목록에 등장, 행 클릭 → `/asset/:id` 진입, 헤더에 "관심" 뱃지(보유요약 없음)
- 자산 상세: 일봉/주봉 차트, AI 분석, 텔레그램 발송, 스케줄 저장/삭제가 기존과 동일하게 동작
- 관심종목 삭제 동작

- [ ] **Step 5: 최종 커밋(필요 시)**

수동 스모크에서 수정이 발생하면 해당 변경만 별도 커밋.

---

## Self-Review (작성자 점검 결과)

- **스펙 커버리지**: A-1 분류(Task 1) · A-2 watchlist 엔드포인트(Task 2,3)·detail 엔드포인트(Task 4) · A-3 네비(Task 8) · A-4 관심종목 페이지(Task 6) · A-5 자산 상세 허브(Task 7) · A-6 api.ts(Task 5) · A-7 테스트(Task 1~4,9) 모두 대응됨.
- **Placeholder**: 모든 코드 스텝에 실제 코드/명령 포함. TBD 없음.
- **타입 일관성**: `held_asset_ids`(set[int]), `get_watchlist`(list[dict]), `get_asset_detail`(dict|None), api `AssetDetailOut`/`WatchlistItem`/`HoldingSummary` 키가 백엔드 반환 키(`current_price/change/change_pct/price_status`, `holding_summary.quantity/avg_price/value_krw/profit_loss_krw/profit_loss_pct`, `quote.price/currency/change/change_pct/status`)와 일치.
- **알림 탭**: 스펙 비목표 — 본 계획에 미포함(스펙 B). 허브에 빈 자리도 만들지 않음.
