# 자산군 분류 + 자산군별 비중 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 보유 자산에 단일 자산군(asset_class)을 지정·수정하고, 대시보드에서 자산군별 비중(현금=현금성 포함)을 보여준다.

**Architecture:** `assets`에 `asset_class` 컬럼을 추가하고, asset_type→자산군 기본 매핑(`default_asset_class`, 순수 함수)으로 등록 시 자동 채운다. `get_portfolio`가 자산군별 비중을 집계(`build_allocation`, 순수 함수)해 응답에 `allocation`을 추가한다. 자산 수정은 `PUT /api/assets/{id}`. 프론트는 보유 폼·목록에서 자산군 입력·수정, 대시보드에 자산군별 비중 표를 추가한다.

**Tech Stack:** Python 3.x, FastAPI, async SQLAlchemy 2.0, asyncpg, pydantic v2, pytest / React 18, Vite, TS, Tailwind.

**참조:** spec `docs/superpowers/specs/2026-06-14-asset-class-classification-design.md`. `.venv/bin/python`·`.venv/bin/pytest`, DB 비밀번호 `mook123!`. DB 통합테스트는 `TEST_DATABASE_URL` 미설정 시 skip.

---

## 파일 구조
```
app/
├── services/market/
│   ├── asset_class.py        # 신규: default_asset_class + 표준 목록
│   ├── types.py              # 수정: ResolvedAsset.asset_class
│   └── resolver.py           # 수정: 해석 시 asset_class 채움
├── models/asset.py           # 수정: asset_class 컬럼
├── schemas/
│   ├── market.py             # 수정: ResolvedAssetOut.asset_class
│   ├── asset.py              # 수정: AssetCreate/AssetOut + AssetUpdate
│   └── portfolio.py          # 수정: Position.asset_class, AllocationSlice, PortfolioOut.allocation
├── services/portfolio/portfolio_service.py  # 수정: build_allocation + get_portfolio
└── routers/
    ├── assets.py             # 수정: PUT /{id}
    └── holdings.py           # 수정: with-asset asset_class 저장
frontend/src/
├── api.ts                    # 수정: updateAsset, ASSET_CLASSES, 타입
├── pages/Holdings.tsx        # 수정: 자산군 입력/수정
└── pages/Dashboard.tsx       # 수정: 자산군 컬럼 + 자산군별 비중 표
```

---

## Task 1: default_asset_class 모듈 + ResolvedAsset 필드 + resolver 채움

**Files:** Create `app/services/market/asset_class.py`; Modify `app/services/market/types.py`, `app/services/market/resolver.py`; Modify `tests/test_resolver.py`

- [ ] **Step 1: tests/test_resolver.py 에 테스트 추가** (파일 맨 끝에 append)
```python

from app.services.market.asset_class import default_asset_class


def test_default_asset_class_mapping():
    assert default_asset_class("stock") == "주식"
    assert default_asset_class("etf") == "주식"
    assert default_asset_class("bond") == "채권"
    assert default_asset_class("crypto") == "가상자산"
    assert default_asset_class("commodity") == "원자재"
    assert default_asset_class("etn") == "기타"
    assert default_asset_class(None) == "기타"
    assert default_asset_class("unknown") == "기타"


def test_resolver_fills_asset_class_from_type():
    yf = MagicMock(); yf.resolve.return_value = _ra(asset_type="stock")
    out = AssetResolver(yfinance=yf, pykrx=MagicMock(), manual=MagicMock()).resolve("AAPL", "US")
    assert out.asset.asset_class == "주식"


def test_resolver_bond_hint_fills_asset_class_채권():
    manual = MagicMock()
    manual.resolve.return_value = _ra(asset_type="bond", data_source="manual", current_price=None)
    out = AssetResolver(yfinance=MagicMock(), pykrx=MagicMock(), manual=manual).resolve("KR123", "KR", asset_type_hint="bond")
    assert out.ok is True
    assert out.asset.asset_class == "채권"
```

- [ ] **Step 2: Run `.venv/bin/pytest tests/test_resolver.py -q`** → FAIL (ModuleNotFoundError asset_class / asset has no asset_class).

- [ ] **Step 3: Create app/services/market/asset_class.py**
```python
# 추천 자산군 목록(프론트와 공유 개념). 자유 입력도 허용한다.
ASSET_CLASSES = ["주식", "채권", "현금성", "원자재", "가상자산", "대체투자", "기타"]

_DEFAULT_BY_TYPE = {
    "stock": "주식", "etf": "주식", "fund": "주식", "index": "주식",
    "bond": "채권", "crypto": "가상자산", "commodity": "원자재", "etn": "기타",
}


def default_asset_class(asset_type: str | None) -> str:
    """asset_type에서 기본 자산군을 추정한다. 미지/None은 '기타'."""
    return _DEFAULT_BY_TYPE.get((asset_type or "").lower(), "기타")
```

- [ ] **Step 4: Modify app/services/market/types.py** — `ResolvedAsset`에 필드 추가(맨 아래 두 선택 필드 뒤):
```python
    current_price: float | None = None
    name_en: str | None = None
    asset_class: str | None = None
```

- [ ] **Step 5: Modify app/services/market/resolver.py** — import 추가 후 두 경로에서 asset_class 채움.
  맨 위 import에 추가: `from app.services.market.asset_class import default_asset_class`
  bond 조기 반환 블록을 아래로 교체:
```python
        # 채권/수동 요청은 바로 manual.
        if asset_type_hint == "bond":
            asset = self.providers["manual"].resolve(ticker, market, asset_type_hint)
            if asset is not None:
                asset.asset_class = default_asset_class(asset.asset_type)
            return ResolveResult(ok=True, asset=asset, tried=["manual"])
```
  정상 경로의 성공 블록(`if asset is not None:` 내부)을 아래로 교체:
```python
            if asset is not None:
                # 사용자가 유형을 명시했으면 저장 유형으로 존중한다.
                # (시세·통화·이름·fetch_symbol은 데이터 소스가 채운 값을 유지)
                if asset_type_hint:
                    asset.asset_type = asset_type_hint
                asset.asset_class = default_asset_class(asset.asset_type)
                return ResolveResult(ok=True, asset=asset, tried=tried)
```

- [ ] **Step 6: Run `.venv/bin/pytest tests/test_resolver.py -q`** → 모든 PASS 보고. 그리고 `.venv/bin/pytest -q` 전체 회귀 확인(에러 없이 PASS+skip).

- [ ] **Step 7: Commit**
```bash
git add app/services/market/asset_class.py app/services/market/types.py app/services/market/resolver.py tests/test_resolver.py
git commit -m "feat: default_asset_class mapping + resolver fills asset_class"
```

---

## Task 2: 모델 + 스키마

**Files:** Modify `app/models/asset.py`, `app/schemas/market.py`, `app/schemas/asset.py`, `app/schemas/portfolio.py`

- [ ] **Step 1: app/models/asset.py** — `fetch_symbol` 줄 다음에 추가:
```python
    fetch_symbol: Mapped[str] = mapped_column(String, nullable=False)
    asset_class: Mapped[str | None] = mapped_column(String)
```

- [ ] **Step 2: app/schemas/market.py** — `ResolvedAssetOut`에 필드 추가(name_en 다음):
```python
    current_price: float | None = None
    name_en: str | None = None
    asset_class: str | None = None
```

- [ ] **Step 3: app/schemas/asset.py 전체 교체**
```python
from pydantic import BaseModel


class AssetCreate(BaseModel):
    ticker: str
    name: str
    asset_type: str
    market: str
    currency: str
    data_source: str
    fetch_symbol: str
    name_en: str | None = None
    asset_class: str | None = None


class AssetUpdate(BaseModel):
    name: str | None = None
    asset_class: str | None = None


class ManualPriceUpdate(BaseModel):
    manual_price: float
    manual_price_currency: str


class AssetOut(BaseModel):
    asset_id: int
    ticker: str
    name: str
    asset_type: str
    market: str
    currency: str
    data_source: str
    fetch_symbol: str
    asset_class: str | None = None
    manual_price: float | None = None
    is_active: bool

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: app/schemas/portfolio.py 전체 교체**
```python
from pydantic import BaseModel


class Position(BaseModel):
    asset_id: int
    ticker: str
    name: str
    market: str
    currency: str
    asset_class: str
    quantity: float
    avg_price: float
    current_price: float
    cost_native: float
    value_native: float
    profit_loss_native: float
    cost_krw: float
    value_krw: float
    profit_loss_krw: float
    profit_loss_pct: float
    weight_pct: float
    price_status: str


class CashPosition(BaseModel):
    id: int
    currency: str
    amount: float
    label: str | None = None
    value_krw: float
    weight_pct: float


class AllocationSlice(BaseModel):
    asset_class: str
    value_krw: float
    weight_pct: float


class PortfolioSummary(BaseModel):
    total_value_krw: float
    total_cost_krw: float
    total_profit_loss_krw: float
    total_profit_loss_pct: float
    total_cash_krw: float


class PortfolioOut(BaseModel):
    positions: list[Position]
    cash: list[CashPosition]
    allocation: list[AllocationSlice]
    summary: PortfolioSummary
```

- [ ] **Step 5: Verify**
```bash
.venv/bin/python -c "from app.db import Base; import app.models; print('asset_class' in [c.name for c in Base.metadata.tables['invest.assets'].columns])"   # True
.venv/bin/python -c "import app.schemas.asset, app.schemas.portfolio, app.schemas.market; print('ok')"   # ok
```

- [ ] **Step 6: Commit**
```bash
git add app/models/asset.py app/schemas/market.py app/schemas/asset.py app/schemas/portfolio.py
git commit -m "feat: asset_class on model + schemas (AssetUpdate, Position, AllocationSlice)"
```

---

## Task 3: assets PUT + with-asset asset_class 저장

**Files:** Modify `app/routers/assets.py`, `app/routers/holdings.py`

- [ ] **Step 1: app/routers/assets.py** — import 줄 수정 + PUT 라우트 추가.
  `from app.schemas.asset import AssetCreate, AssetOut, ManualPriceUpdate` 를 아래로 교체:
```python
from app.schemas.asset import AssetCreate, AssetUpdate, AssetOut, ManualPriceUpdate
```
  `list_assets` 함수 정의 바로 위(또는 아래 아무 곳, create_asset 다음)에 PUT 라우트 추가:
```python
@router.put("/{asset_id}", response_model=AssetOut)
async def update_asset(asset_id: int, body: AssetUpdate, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    data = body.model_dump(exclude_unset=True)
    if "asset_class" in data:
        ac = data["asset_class"]
        asset.asset_class = ac.strip() if (ac and ac.strip()) else None
    if "name" in data and data["name"]:
        asset.name = data["name"]
    await db.commit()
    await db.refresh(asset)
    return asset
```

- [ ] **Step 2: app/routers/holdings.py** — with-asset 자산 생성 시 asset_class 저장.
  import에 추가: `from app.services.market.asset_class import default_asset_class`
  `create_with_asset`의 신규 Asset 생성 블록을 아래로 교체:
```python
    if asset is None:
        asset = Asset(
            ticker=body.ticker, name=body.name, asset_type=body.asset_type, market=body.market,
            currency=body.currency, data_source=body.data_source, fetch_symbol=body.fetch_symbol,
            name_en=body.name_en,
            asset_class=body.asset_class or default_asset_class(body.asset_type),
        )
        db.add(asset)
        await db.flush()   # asset_id 확보(커밋 전)
```

- [ ] **Step 3: Verify routes**
```bash
.venv/bin/python -c "from app.routers.assets import router; print(any(r.path=='/api/assets/{asset_id}' and 'PUT' in r.methods for r in router.routes))"   # True
.venv/bin/python -c "from app.main import app; print('ok')"
```

- [ ] **Step 4: Commit**
```bash
git add app/routers/assets.py app/routers/holdings.py
git commit -m "feat: PUT /api/assets/{id} (asset_class/name) + store asset_class on with-asset"
```

---

## Task 4: build_allocation + get_portfolio 집계

**Files:** Modify `app/services/portfolio/portfolio_service.py`; Modify `tests/test_portfolio_service.py`

- [ ] **Step 1: tests/test_portfolio_service.py 에 append**
```python

from app.services.portfolio.portfolio_service import build_allocation


def test_build_allocation_groups_by_class_and_adds_cash():
    positions = [
        {"asset_class": "주식", "value_krw": 600.0},
        {"asset_class": "채권", "value_krw": 300.0},
        {"asset_class": "주식", "value_krw": 100.0},
    ]
    total_cash = 200.0
    total_value = 1200.0  # 1000 종목 + 200 현금
    alloc = build_allocation(positions, total_cash, total_value)
    by = {a["asset_class"]: a for a in alloc}
    assert by["주식"]["value_krw"] == 700.0
    assert round(by["주식"]["weight_pct"], 4) == round(700/1200*100, 4)
    assert by["채권"]["value_krw"] == 300.0
    assert by["현금성"]["value_krw"] == 200.0
    # 평가액 desc 정렬
    assert [a["asset_class"] for a in alloc] == ["주식", "채권", "현금성"]


def test_build_allocation_null_class_is_기타():
    alloc = build_allocation([{"asset_class": None, "value_krw": 50.0}], 0.0, 50.0)
    assert alloc[0]["asset_class"] == "기타"
    assert alloc[0]["weight_pct"] == 100.0
```

- [ ] **Step 2: Run `.venv/bin/pytest tests/test_portfolio_service.py -q`** → FAIL (no build_allocation).

- [ ] **Step 3: portfolio_service.py** — `aggregate_position` 함수 정의 바로 아래(import 블록 위)에 추가:
```python
def build_allocation(positions: list[dict], total_cash: float, total_value: float) -> list[dict]:
    """자산군별 평가액·비중을 집계한다. 현금은 '현금성' 자산군으로 더한다.
    asset_class가 None/빈값이면 '기타'로 묶는다."""
    sums: dict[str, float] = {}
    for p in positions:
        key = p.get("asset_class") or "기타"
        sums[key] = sums.get(key, 0.0) + p["value_krw"]
    if total_cash:
        sums["현금성"] = sums.get("현금성", 0.0) + total_cash
    out = [{"asset_class": k, "value_krw": v,
            "weight_pct": (v / total_value * 100) if total_value else 0} for k, v in sums.items()]
    out.sort(key=lambda x: x["value_krw"], reverse=True)
    return out
```

- [ ] **Step 4: portfolio_service.py — get_portfolio 수정** (2곳):
  (a) position dict에 asset_class 포함 — positions.append({...}) 의 메타 부분을 아래로 교체:
```python
        positions.append({
            "asset_id": asset.asset_id, "ticker": asset.ticker, "name": asset.name,
            "market": asset.market, "currency": asset.currency,
            "asset_class": asset.asset_class or "기타",
            "current_price": quote.price, "price_status": quote.status, **agg,
        })
```
  (b) return 직전에 allocation 계산 후 응답에 포함 — `total_cost = sum(...)` 줄부터 끝까지를 아래로 교체:
```python
    total_cost = sum(p["cost_krw"] for p in positions)
    positions_value = total_value - total_cash   # 종목 평가액 합(현금 제외)
    allocation = build_allocation(positions, total_cash, total_value)
    return {
        "positions": positions,
        "cash": cash,
        "allocation": allocation,
        "summary": {
            "total_value_krw": total_value,
            "total_cost_krw": total_cost,
            "total_profit_loss_krw": positions_value - total_cost,
            "total_profit_loss_pct": ((positions_value - total_cost) / total_cost * 100) if total_cost else 0,
            "total_cash_krw": total_cash,
        },
    }
```

- [ ] **Step 5: Run `.venv/bin/pytest tests/test_portfolio_service.py -q`** → PASS. 그리고 `.venv/bin/pytest -q` 전체 회귀(PASS+skip). 또 import 확인:
```bash
.venv/bin/python -c "from app.services.portfolio.portfolio_service import get_portfolio, build_allocation, aggregate_position; print('ok')"
```

- [ ] **Step 6: Commit**
```bash
git add app/services/portfolio/portfolio_service.py tests/test_portfolio_service.py
git commit -m "feat: build_allocation + asset_class in positions, allocation in portfolio"
```

---

## Task 5: 개발 DB 마이그레이션 (asset_class 컬럼 + backfill) — 수동/개발 전용

**Files:** 없음(런타임 DB 작업)

`ensure_schema()`는 생성 전용이라 기존 `invest.assets`에 컬럼을 추가하지 못한다. 비파괴 ALTER로 컬럼을 추가하고 기존 자산을 backfill한다(실데이터 보존).

- [ ] **Step 1: ALTER + backfill**
```bash
.venv/bin/python - <<'PY'
import asyncio, asyncpg
from app.services.market.asset_class import default_asset_class
async def main():
    c = await asyncpg.connect(host="100.114.126.67", port=5432, user="ai_agent",
                              password="mook123!", database="agent_db")
    await c.execute("ALTER TABLE invest.assets ADD COLUMN IF NOT EXISTS asset_class TEXT")
    rows = await c.fetch("SELECT asset_id, asset_type FROM invest.assets WHERE asset_class IS NULL")
    for r in rows:
        await c.execute("UPDATE invest.assets SET asset_class=$1 WHERE asset_id=$2",
                        default_asset_class(r["asset_type"]), r["asset_id"])
    print("backfilled", len(rows), "assets")
    for r in await c.fetch("SELECT ticker, asset_type, asset_class FROM invest.assets ORDER BY asset_id"):
        print(" ", dict(r))
    await c.close()
asyncio.run(main())
PY
```
DB 접속 불가 시 중단·보고(BLOCKED). 단위 테스트와 무관.

- [ ] **Step 2:** (커밋 없음)

---

## Task 6: 프론트 api.ts

**Files:** Modify `frontend/src/api.ts`

- [ ] **Step 1: api 객체에 updateAsset 추가** (`updateHolding` 다음 줄):
```ts
  updateAsset: (id: number, a: any) =>
    j(`/api/assets/${id}`, { method: "PUT", body: JSON.stringify(a) }),
```

- [ ] **Step 2: 파일 상단(`const BASE = "";` 아래)에 추천 자산군 상수 추가:**
```ts
export const ASSET_CLASSES = ["주식", "채권", "현금성", "원자재", "가상자산", "대체투자", "기타"];
```

- [ ] **Step 3: 타입 수정** — `Position`에 `asset_class` 추가, `AllocationSlice` 추가, `PortfolioOut`에 `allocation` 추가. 세 블록을 아래로 교체:
```ts
export interface Position {
  asset_id: number; ticker: string; name: string; market: string; currency: string;
  asset_class: string;
  quantity: number; avg_price: number; current_price: number;
  cost_native: number; value_native: number; profit_loss_native: number;
  cost_krw: number; value_krw: number; profit_loss_krw: number; profit_loss_pct: number;
  weight_pct: number; price_status: string;
}
export interface CashPosition {
  id: number; currency: string; amount: number; label: string | null;
  value_krw: number; weight_pct: number;
}
export interface AllocationSlice {
  asset_class: string; value_krw: number; weight_pct: number;
}
export interface PortfolioOut {
  positions: Position[];
  cash: CashPosition[];
  allocation: AllocationSlice[];
  summary: { total_value_krw: number; total_cost_krw: number;
             total_profit_loss_krw: number; total_profit_loss_pct: number; total_cash_krw: number };
}
```

- [ ] **Step 4: Build** → `cd frontend && npm run build 2>&1 | tail -2` → 성공.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/api.ts
git commit -m "feat(frontend): updateAsset, ASSET_CLASSES, asset_class/allocation types"
```

---

## Task 7: Holdings.tsx — 자산군 입력/수정

**Files:** Modify `frontend/src/pages/Holdings.tsx` (전체 교체)

- [ ] **Step 1: frontend/src/pages/Holdings.tsx 전체 교체**
```tsx
import { useEffect, useState } from "react";
import { api, ASSET_CLASSES } from "../api";
import type { ResolveResponse } from "../api";

const MARKETS = ["US", "KR", "JP", "CRYPTO"];
const CURRENCIES = ["KRW", "USD", "JPY"];
const ASSET_TYPES = [
  { code: "", label: "자동 감지" }, { code: "stock", label: "주식" },
  { code: "etf", label: "ETF" }, { code: "bond", label: "채권 (수동가격)" },
  { code: "commodity", label: "원자재" }, { code: "crypto", label: "가상자산" },
];

const emptyLot = { quantity: "", purchase_price: "", purchase_date: "", fee: "", memo: "", asset_class: "" };
const emptyCash = { currency: "KRW", amount: "", label: "" };

export default function Holdings() {
  const [assets, setAssets] = useState<any[]>([]);
  const [holdings, setHoldings] = useState<any[]>([]);
  const [cash, setCash] = useState<any[]>([]);
  const [ticker, setTicker] = useState(""); const [market, setMarket] = useState("US");
  const [assetType, setAssetType] = useState("");
  const [preview, setPreview] = useState<ResolveResponse | null>(null);
  const [lot, setLot] = useState<any>({ ...emptyLot });
  const [cashForm, setCashForm] = useState<any>({ ...emptyCash });
  const [editHid, setEditHid] = useState<number | null>(null);
  const [editH, setEditH] = useState<any>({ ...emptyLot });
  const [editCid, setEditCid] = useState<number | null>(null);
  const [editC, setEditC] = useState<any>({ ...emptyCash });

  const load = async () => {
    setAssets(await api.listAssets());
    setHoldings(await api.listHoldings());
    setCash(await api.listCash());
  };
  useEffect(() => { load(); }, []);

  const assetById = Object.fromEntries(assets.map((a) => [a.asset_id, a]));

  const doResolve = async () => {
    const res = await api.resolve(ticker, market, assetType || undefined);
    setPreview(res);
    if (res.ok && res.asset) setLot({ ...emptyLot, asset_class: res.asset.asset_class ?? "" });
  };
  const addNew = async () => {
    if (!preview?.asset) return;
    await api.createHoldingWithAsset({
      ...preview.asset, asset_class: lot.asset_class || null,
      quantity: Number(lot.quantity), purchase_price: Number(lot.purchase_price),
      purchase_date: lot.purchase_date || null, fee: Number(lot.fee || 0), memo: lot.memo || null,
    });
    setPreview(null); setTicker(""); setLot({ ...emptyLot });
    await load();
  };

  const addCash = async () => {
    await api.createCash({ currency: cashForm.currency, amount: Number(cashForm.amount), label: cashForm.label || null });
    setCashForm({ ...emptyCash });
    await load();
  };

  const startEditH = (h: any) => {
    setEditHid(h.holding_id);
    setEditH({ quantity: h.quantity, purchase_price: h.purchase_price,
      purchase_date: h.purchase_date ?? "", fee: h.fee, memo: h.memo ?? "",
      asset_class: assetById[h.asset_id]?.asset_class ?? "" });
  };
  const saveH = async (h: any) => {
    await api.updateAsset(h.asset_id, { asset_class: editH.asset_class || null });
    await api.updateHolding(editHid!, {
      quantity: Number(editH.quantity), purchase_price: Number(editH.purchase_price),
      purchase_date: editH.purchase_date || null, fee: Number(editH.fee || 0), memo: editH.memo || null });
    setEditHid(null); await load();
  };
  const removeH = async (id: number) => { await api.deleteHolding(id); await load(); };

  const startEditC = (c: any) => { setEditCid(c.id); setEditC({ currency: c.currency, amount: c.amount, label: c.label ?? "" }); };
  const saveC = async () => {
    await api.updateCash(editCid!, { currency: editC.currency, amount: Number(editC.amount), label: editC.label || null });
    setEditCid(null); await load();
  };
  const removeC = async (id: number) => { await api.deleteCash(id); await load(); };

  const inp = "border rounded px-2 py-1";

  return (
    <div className="p-6 space-y-8">
      <datalist id="asset-classes">{ASSET_CLASSES.map((c) => <option key={c} value={c} />)}</datalist>

      <div className="space-y-6">
        <h1 className="text-xl font-bold">보유 추가</h1>

        <section className="space-y-2">
          <h2 className="font-semibold text-gray-700">종목</h2>
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
          </div>
          {preview && (preview.ok && preview.asset ? (
            <div className="rounded border p-3 bg-green-50 space-y-2">
              <div><b>{preview.asset.name}</b> · {preview.asset.currency} · {preview.asset.asset_type} · 현재가 {preview.asset.current_price ?? "—"}</div>
              <div className="flex gap-2 flex-wrap">
                <input className={`${inp} w-24`} placeholder="수량"
                  value={lot.quantity} onChange={(e) => setLot({ ...lot, quantity: e.target.value })} />
                <input className={`${inp} w-32`} placeholder={`매입단가 (${preview.asset.currency})`}
                  value={lot.purchase_price} onChange={(e) => setLot({ ...lot, purchase_price: e.target.value })} />
                <input type="date" className={inp} title="매입일(선택)"
                  value={lot.purchase_date} onChange={(e) => setLot({ ...lot, purchase_date: e.target.value })} />
                <input className={`${inp} w-24`} placeholder="수수료"
                  value={lot.fee} onChange={(e) => setLot({ ...lot, fee: e.target.value })} />
                <input list="asset-classes" className={`${inp} w-28`} placeholder="자산군"
                  value={lot.asset_class} onChange={(e) => setLot({ ...lot, asset_class: e.target.value })} />
                <input className={inp} placeholder="메모"
                  value={lot.memo} onChange={(e) => setLot({ ...lot, memo: e.target.value })} />
                <button onClick={addNew} className="px-3 py-1 rounded bg-blue-600 text-white">추가</button>
              </div>
              <div className="text-xs text-gray-500">같은 티커를 다시 추가하면 기존 자산에 분할매수로 쌓입니다.</div>
            </div>
          ) : (
            <div className="rounded border p-3 bg-amber-50">
              <div>조회 실패 (시도: {preview.tried.join(", ")})</div>
              <div className="text-sm text-gray-600">{preview.suggestion}</div>
            </div>
          ))}
        </section>

        <section className="space-y-2">
          <h2 className="font-semibold text-gray-700">현금</h2>
          <div className="flex gap-2 flex-wrap items-center">
            <select className={inp} value={cashForm.currency}
              onChange={(e) => setCashForm({ ...cashForm, currency: e.target.value })}>
              {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
            </select>
            <input className={`${inp} w-40`} placeholder="금액"
              value={cashForm.amount} onChange={(e) => setCashForm({ ...cashForm, amount: e.target.value })} />
            <input className={inp} placeholder="라벨(예: 증권사 예수금)"
              value={cashForm.label} onChange={(e) => setCashForm({ ...cashForm, label: e.target.value })} />
            <button onClick={addCash} className="px-3 py-1 rounded bg-blue-600 text-white">추가</button>
          </div>
        </section>
      </div>

      <section>
        <h2 className="font-semibold mb-2">보유 종목</h2>
        <table className="w-full text-sm">
          <thead><tr className="border-b text-left text-gray-500">
            <th className="py-2">종목</th><th>자산군</th><th>매입일</th><th>수량</th><th>단가</th><th>수수료</th><th>메모</th><th></th>
          </tr></thead>
          <tbody>
            {holdings.map((h) => {
              const a = assetById[h.asset_id];
              const editing = editHid === h.holding_id;
              return (
                <tr key={h.holding_id} className="border-b">
                  <td className="py-2">{a ? `${a.name} (${a.ticker}·${a.market})` : `#${h.asset_id}`}</td>
                  {editing ? (
                    <>
                      <td><input list="asset-classes" className={`${inp} w-24`} value={editH.asset_class}
                        onChange={(e) => setEditH({ ...editH, asset_class: e.target.value })} /></td>
                      <td><input type="date" className={`${inp} w-36`} value={editH.purchase_date}
                        onChange={(e) => setEditH({ ...editH, purchase_date: e.target.value })} /></td>
                      <td><input className={`${inp} w-20`} value={editH.quantity}
                        onChange={(e) => setEditH({ ...editH, quantity: e.target.value })} /></td>
                      <td><input className={`${inp} w-24`} value={editH.purchase_price}
                        onChange={(e) => setEditH({ ...editH, purchase_price: e.target.value })} /></td>
                      <td><input className={`${inp} w-20`} value={editH.fee}
                        onChange={(e) => setEditH({ ...editH, fee: e.target.value })} /></td>
                      <td><input className={`${inp} w-28`} value={editH.memo}
                        onChange={(e) => setEditH({ ...editH, memo: e.target.value })} /></td>
                      <td className="whitespace-nowrap">
                        <button onClick={() => saveH(h)} className="text-blue-600 mr-2">저장</button>
                        <button onClick={() => setEditHid(null)} className="text-gray-500">취소</button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td>{a?.asset_class ?? "—"}</td>
                      <td>{h.purchase_date ?? "—"}</td><td>{h.quantity}</td><td>{h.purchase_price}</td>
                      <td>{h.fee}</td><td>{h.memo ?? "—"}</td>
                      <td className="whitespace-nowrap">
                        <button onClick={() => startEditH(h)} className="text-gray-700 mr-2">수정</button>
                        <button onClick={() => removeH(h.holding_id)} className="text-red-600">삭제</button>
                      </td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <section>
        <h2 className="font-semibold mb-2">현금</h2>
        <table className="w-full text-sm">
          <thead><tr className="border-b text-left text-gray-500">
            <th className="py-2">통화</th><th>금액</th><th>라벨</th><th></th>
          </tr></thead>
          <tbody>
            {cash.map((c) => {
              const editing = editCid === c.id;
              return (
                <tr key={c.id} className="border-b">
                  {editing ? (
                    <>
                      <td className="py-2"><select className={inp} value={editC.currency}
                        onChange={(e) => setEditC({ ...editC, currency: e.target.value })}>
                        {CURRENCIES.map((x) => <option key={x}>{x}</option>)}
                      </select></td>
                      <td><input className={`${inp} w-32`} value={editC.amount}
                        onChange={(e) => setEditC({ ...editC, amount: e.target.value })} /></td>
                      <td><input className={inp} value={editC.label}
                        onChange={(e) => setEditC({ ...editC, label: e.target.value })} /></td>
                      <td className="whitespace-nowrap">
                        <button onClick={saveC} className="text-blue-600 mr-2">저장</button>
                        <button onClick={() => setEditCid(null)} className="text-gray-500">취소</button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="py-2">{c.currency}</td><td>{Number(c.amount).toLocaleString()}</td>
                      <td>{c.label ?? "—"}</td>
                      <td className="whitespace-nowrap">
                        <button onClick={() => startEditC(c)} className="text-gray-700 mr-2">수정</button>
                        <button onClick={() => removeC(c.id)} className="text-red-600">삭제</button>
                      </td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Build** → `cd frontend && npm run build 2>&1 | tail -2` → 성공.

- [ ] **Step 3: Commit**
```bash
git add frontend/src/pages/Holdings.tsx
git commit -m "feat(frontend): asset_class input on add + inline edit in holdings list"
```

---

## Task 8: Dashboard.tsx — 자산군 컬럼 + 자산군별 비중 표

**Files:** Modify `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: 포지션 테이블에 자산군 컬럼 추가.**
  thead의 `<th className="py-2">종목</th>` 다음에 `<th>자산군</th>` 삽입:
```tsx
          <th className="py-2">종목</th><th>자산군</th><th>수량</th><th>평단</th><th>현재가</th>
```
  tbody 각 행에서 종목 `<td>` 다음에 자산군 셀 삽입(수량 td 앞):
```tsx
              <td className="py-2">{p.name} <span className="text-gray-400">{p.ticker}·{p.market}</span></td>
              <td>{p.asset_class}</td>
              <td>{p.quantity}</td><td>{p.avg_price.toLocaleString()}</td>
```

- [ ] **Step 2: 현금 표 다음(컴포넌트 최상위 `</div>` 직전)에 자산군별 비중 표 추가:**
```tsx
      {data.allocation.length > 0 && (
        <div>
          <h2 className="font-semibold mb-2">자산군별 비중</h2>
          <table className="w-full text-sm border-collapse">
            <thead><tr className="border-b text-left text-gray-500">
              <th className="py-2">자산군</th><th>평가액(KRW)</th><th>비중</th>
            </tr></thead>
            <tbody>
              {data.allocation.map((a) => (
                <tr key={a.asset_class} className="border-b">
                  <td className="py-2">{a.asset_class}</td><td>₩{krw(a.value_krw)}</td><td>{a.weight_pct.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
```

- [ ] **Step 3: Build** → `cd frontend && npm run build 2>&1 | tail -2` → 성공.

- [ ] **Step 4: Commit**
```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(frontend): asset_class column + allocation-by-class table on dashboard"
```

---

## Task 9: 최종 검증

**Files:** 없음

- [ ] **Step 1: 백엔드 단위 스위트** → `.venv/bin/pytest -q` → 모든 PASS(+DB skip), 에러 없음.
- [ ] **Step 2: 앱 import** → `.venv/bin/python -c "from app.main import app; print(len(app.routes),'routes')"` 정상(assets PUT 추가).
- [ ] **Step 3: 프론트 빌드** → `cd frontend && npm run build 2>&1 | tail -2` 성공.
- [ ] **Step 4: (DB 접속 시) 실DB 스모크.** 앱 부팅 후: `PUT /api/assets/{id}`로 기존 자산의 asset_class를 "채권" 등으로 변경 → `GET /api/portfolio`의 `positions[].asset_class`·`allocation`·현금=현금성 확인. with-asset로 임시 자산 등록 시 asset_class 기본값 확인 후 임시분 정리(사용자 실데이터 보존). DB 불가 시 skip·보고.
- [ ] **Step 5:** (커밋 없음)

---

## Self-Review (spec 대비)
- spec §2 자산군 값·매핑 → Task 1(`asset_class.py`, default_asset_class). ✅
- spec §3 데이터 모델(asset_class 컬럼) → Task 2 + Task 5 마이그레이션/backfill. ✅
- spec §4.1 default_asset_class → Task 1. §4.2 ResolvedAsset/resolve(채권·정상 경로) → Task 1. §4.3 스키마 → Task 2. §4.4 라우터(PUT, with-asset) → Task 3. §4.5 집계 → Task 4. ✅
- spec §5 프론트(api/Holdings/Dashboard) → Task 6·7·8. ✅
- spec §6 테스트 → Task 1·4 단위 + Task 9 스모크. ✅
- spec §7 오류(PUT 404, 빈 문자열→None, total 0 방어) → Task 3(update_asset 정규화·404), Task 4(weight 방어). ✅

타입 일관성: `asset_class`가 ResolvedAsset → ResolvedAssetOut → AssetCreate/HoldingWithAssetCreate/AssetOut → Position → api.ts Position 전반에서 동일 명칭. `allocation`/`AllocationSlice`(asset_class/value_krw/weight_pct)가 build_allocation 반환·portfolio 스키마·api.ts·Dashboard에서 일치. `default_asset_class`가 resolver·holdings·migration에서 동일 사용.
