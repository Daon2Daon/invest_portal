# 현금 자산군 + 보유종목 등록 정비 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 현금을 자산군으로 입력 가능하게 하고, 보유종목 등록을 단일 흐름으로 통합하며, 매입날짜를 선택값으로 바꾸고, 환율 모델을 단순화(매수시점 환율 제거, 현재 환율로 KRW 환산)한다.

**Architecture:** 기존 1단계 백엔드(FastAPI + async SQLAlchemy + PostgreSQL)와 React SPA에 (1) `cash_balances` 테이블·서비스·라우터·UI를 추가하고, (2) `holdings`에서 `purchase_fx_rate`를 제거하고 `purchase_date`를 nullable로 바꾸며, (3) `portfolio_service`의 손익 계산을 자산 통화 기준 + 현재 환율 환산으로 단순화하고, (4) 자산 upsert + 보유 생성을 한 번에 처리하는 `with-asset` 엔드포인트와 통합 폼을 만든다.

**Tech Stack:** Python 3.x, FastAPI, SQLAlchemy 2.0(async), asyncpg, pydantic v2, pytest / React 18, Vite, TS, Tailwind.

**참조:** spec `docs/superpowers/specs/2026-06-14-cash-and-holdings-refinements-design.md`. 개발 환경: `.venv/bin/python`·`.venv/bin/pytest`, 로컬 `.env`(DB 비밀번호 `mook123!`). DB 통합테스트는 `TEST_DATABASE_URL` 미설정 시 skip(설계대로).

---

## 파일 구조

```
app/
├── models/
│   ├── holding.py            # 수정: purchase_fx_rate 제거, purchase_date nullable
│   ├── cash_balance.py       # 신규: CashBalance
│   └── __init__.py           # 수정: CashBalance export
├── bootstrap.py              # 변경 없음 (app.models import로 자동 등록)
├── schemas/
│   ├── holding.py            # 수정: fx_rate 제거, date 선택, HoldingWithAssetCreate 추가
│   ├── cash.py               # 신규
│   └── portfolio.py          # 수정: Position native 필드, CashPosition, summary total_cash
├── services/portfolio/portfolio_service.py  # 수정: 손익 단순화 + 현금 통합
├── routers/
│   ├── holdings.py           # 수정: fx 자동채움 제거, with-asset 추가
│   └── cash.py               # 신규
└── main.py                   # 수정: cash 라우터 등록
frontend/src/
├── api.ts                    # 수정: cash·with-asset·타입
├── pages/Holdings.tsx        # 수정: 통합 폼(resolve 포함), 날짜 선택
├── pages/Cash.tsx            # 신규
├── pages/Dashboard.tsx       # 수정: 현금 섹션
└── App.tsx                   # 수정: /cash 라우트·네비
```

---

## Task 1: holdings 모델·스키마 단순화 (fx_rate 제거, date 선택)

**Files:**
- Modify: `app/models/holding.py`
- Modify: `app/schemas/holding.py`

- [ ] **Step 1: app/models/holding.py 수정 (purchase_fx_rate 제거, purchase_date nullable)**

`purchase_date` 줄과 `purchase_fx_rate` 줄을 아래로 교체:
```python
    purchase_date: Mapped[date | None] = mapped_column(Date)
    quantity: Mapped[float] = mapped_column(Numeric, nullable=False)
    purchase_price: Mapped[float] = mapped_column(Numeric, nullable=False)
    fee: Mapped[float] = mapped_column(Numeric, default=0)
```
(즉 `purchase_fx_rate` 줄을 완전히 삭제하고, `purchase_date`의 `nullable=False`를 제거해 nullable로.)

- [ ] **Step 2: app/schemas/holding.py 전체 교체**

```python
from datetime import date
from pydantic import BaseModel


class HoldingCreate(BaseModel):
    asset_id: int
    quantity: float
    purchase_price: float
    purchase_date: date | None = None
    fee: float = 0
    memo: str | None = None


class HoldingWithAssetCreate(BaseModel):
    # 자산 필드 (resolve 결과)
    ticker: str
    name: str
    asset_type: str
    market: str
    currency: str
    data_source: str
    fetch_symbol: str
    name_en: str | None = None
    # 보유 필드
    quantity: float
    purchase_price: float
    purchase_date: date | None = None
    fee: float = 0
    memo: str | None = None


class HoldingUpdate(BaseModel):
    quantity: float | None = None
    purchase_price: float | None = None
    purchase_date: date | None = None
    fee: float | None = None
    memo: str | None = None


class HoldingOut(BaseModel):
    holding_id: int
    asset_id: int
    quantity: float
    purchase_price: float
    purchase_date: date | None = None
    fee: float
    memo: str | None = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: import 확인**

Run: `.venv/bin/python -c "import app.models, app.schemas.holding; print('ok')"` → `ok`

- [ ] **Step 4: Commit**
```bash
git add app/models/holding.py app/schemas/holding.py
git commit -m "refactor: drop purchase_fx_rate, make purchase_date optional in holdings"
```

---

## Task 2: portfolio aggregate_position 단순화 (자산통화 기준 + 현재환율)

**Files:**
- Modify: `app/services/portfolio/portfolio_service.py` (aggregate_position 함수만)
- Modify: `tests/test_portfolio_service.py`

- [ ] **Step 1: tests/test_portfolio_service.py 전체 교체 (새 의미 반영)**

```python
from app.services.portfolio.portfolio_service import aggregate_position


def test_aggregate_position_single_lot_krw():
    lots = [dict(quantity=10, purchase_price=70000, fee=0)]
    pos = aggregate_position(lots, current_price=71000, fx_now=1.0)
    assert pos["quantity"] == 10
    assert pos["avg_price"] == 70000
    assert pos["cost_native"] == 700000
    assert pos["value_native"] == 710000
    assert pos["cost_krw"] == 700000
    assert pos["value_krw"] == 710000
    assert pos["profit_loss_krw"] == 10000
    assert round(pos["profit_loss_pct"], 4) == round(10000 / 700000 * 100, 4)


def test_aggregate_position_usd_uses_current_fx_for_both_cost_and_value():
    # 매수시점 환율을 쓰지 않는다: 원가·평가액 모두 현재 환율(1350)로 환산.
    # cost_native=1000, value_native=1100 → cost_krw=1,350,000, value_krw=1,485,000, pl_krw=135,000
    lots = [dict(quantity=10, purchase_price=100, fee=0)]
    pos = aggregate_position(lots, current_price=110, fx_now=1350.0)
    assert pos["cost_native"] == 1000
    assert pos["value_native"] == 1100
    assert pos["profit_loss_native"] == 100
    assert pos["cost_krw"] == 1350000
    assert pos["value_krw"] == 1485000
    assert pos["profit_loss_krw"] == 135000
    assert pos["profit_loss_pct"] == 10.0


def test_aggregate_position_fee_added_to_cost():
    lots = [dict(quantity=10, purchase_price=100, fee=50)]
    pos = aggregate_position(lots, current_price=100, fx_now=1.0)
    assert pos["cost_native"] == 1050  # 1000 + 50 수수료
    assert pos["value_native"] == 1000
    assert pos["profit_loss_native"] == -50


def test_aggregate_position_multi_lot_weighted_avg():
    lots = [
        dict(quantity=10, purchase_price=100, fee=0),
        dict(quantity=30, purchase_price=200, fee=0),
    ]
    pos = aggregate_position(lots, current_price=200, fx_now=1.0)
    assert pos["quantity"] == 40
    assert pos["avg_price"] == (10 * 100 + 30 * 200) / 40  # 175
```

- [ ] **Step 2: 실패 확인** → Run: `.venv/bin/pytest tests/test_portfolio_service.py -v` → 일부 FAIL(키 cost_native 없음 등).

- [ ] **Step 3: portfolio_service.py 의 aggregate_position 함수 교체**

기존 `aggregate_position` 함수 전체를 아래로 교체(이후의 import·get_portfolio는 Task 5에서 다룸):
```python
def aggregate_position(lots: list[dict], current_price: float, fx_now: float) -> dict:
    """동일 자산의 lot들을 자산 통화 기준으로 집계하고 현재 환율(fx_now)로 KRW 환산한다.

    매수시점 환율은 쓰지 않는다(해외 자산 과거가치 산정 불필요).
    cost_native  = Σ (quantity * purchase_price) + fee
    value_native = Σ quantity * current_price
    *_krw        = *_native * fx_now
    """
    total_qty = sum(l["quantity"] for l in lots)
    cost_native = sum(l["quantity"] * l["purchase_price"] + (l.get("fee") or 0) for l in lots)
    value_native = total_qty * current_price
    avg_price = (sum(l["quantity"] * l["purchase_price"] for l in lots) / total_qty) if total_qty else 0
    pl_native = value_native - cost_native
    pl_pct = (pl_native / cost_native * 100) if cost_native else 0
    return {
        "quantity": total_qty,
        "avg_price": avg_price,
        "cost_native": cost_native,
        "value_native": value_native,
        "profit_loss_native": pl_native,
        "cost_krw": cost_native * fx_now,
        "value_krw": value_native * fx_now,
        "profit_loss_krw": pl_native * fx_now,
        "profit_loss_pct": pl_pct,
    }
```

- [ ] **Step 4: 통과 확인** → Run: `.venv/bin/pytest tests/test_portfolio_service.py -v` → 4 PASS.

- [ ] **Step 5: Commit**
```bash
git add app/services/portfolio/portfolio_service.py tests/test_portfolio_service.py
git commit -m "refactor: simplify P&L to native currency + current-FX conversion"
```

---

## Task 3: CashBalance 모델

**Files:**
- Create: `app/models/cash_balance.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: app/models/cash_balance.py 생성**

```python
from datetime import datetime
from sqlalchemy import String, Numeric, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CashBalance(Base):
    __tablename__ = "cash_balances"

    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[str] = mapped_column(String, nullable=False)   # KRW/USD/JPY 등
    amount: Mapped[float] = mapped_column(Numeric, nullable=False)
    label: Mapped[str | None] = mapped_column(String)              # "증권사 예수금" 등
    memo: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 2: app/models/__init__.py 교체**

```python
from app.models.asset import Asset
from app.models.exchange_rate import ExchangeRate
from app.models.price_snapshot import PriceSnapshot
from app.models.holding import Holding
from app.models.app_setting import AppSetting
from app.models.cash_balance import CashBalance

__all__ = ["Asset", "ExchangeRate", "PriceSnapshot", "Holding", "AppSetting", "CashBalance"]
```

- [ ] **Step 3: 메타데이터 등록 확인**

Run: `.venv/bin/python -c "from app.db import Base; import app.models; print('invest.cash_balances' in Base.metadata.tables)"` → `True`

- [ ] **Step 4: Commit**
```bash
git add app/models/cash_balance.py app/models/__init__.py
git commit -m "feat: CashBalance model"
```

---

## Task 4: cash·portfolio 스키마

**Files:**
- Create: `app/schemas/cash.py`
- Modify: `app/schemas/portfolio.py`

- [ ] **Step 1: app/schemas/cash.py 생성**

```python
from pydantic import BaseModel


class CashCreate(BaseModel):
    currency: str
    amount: float
    label: str | None = None
    memo: str | None = None


class CashUpdate(BaseModel):
    currency: str | None = None
    amount: float | None = None
    label: str | None = None
    memo: str | None = None


class CashOut(BaseModel):
    id: int
    currency: str
    amount: float
    label: str | None = None
    memo: str | None = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: app/schemas/portfolio.py 전체 교체 (Position native 필드 + CashPosition + summary)**

```python
from pydantic import BaseModel


class Position(BaseModel):
    asset_id: int
    ticker: str
    name: str
    market: str
    currency: str
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


class PortfolioSummary(BaseModel):
    total_value_krw: float
    total_cost_krw: float
    total_profit_loss_krw: float
    total_profit_loss_pct: float
    total_cash_krw: float


class PortfolioOut(BaseModel):
    positions: list[Position]
    cash: list[CashPosition]
    summary: PortfolioSummary
```

- [ ] **Step 3: import 확인**

Run: `.venv/bin/python -c "import app.schemas.cash, app.schemas.portfolio; print('ok')"` → `ok`

- [ ] **Step 4: Commit**
```bash
git add app/schemas/cash.py app/schemas/portfolio.py
git commit -m "feat: cash schema + portfolio schema with cash and native fields"
```

---

## Task 5: get_portfolio — native 집계 + 현금 통합

**Files:**
- Modify: `app/services/portfolio/portfolio_service.py` (aggregate_position 아래 부분)

- [ ] **Step 1: portfolio_service.py 의 import·get_portfolio 블록 교체**

`aggregate_position` 함수 정의 아래의 모든 코드(import 문들 + `get_portfolio`)를 아래로 교체:
```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Asset, Holding, CashBalance
from app.services.market.quote_service import get_quote
from app.services.fx.fx_service import get_rate_to_krw


async def get_portfolio(db: AsyncSession) -> dict:
    assets = (await db.execute(select(Asset).where(Asset.is_active == True))).scalars().all()  # noqa: E712
    positions = []
    total_value = 0.0
    for asset in assets:
        lots = (await db.execute(
            select(Holding).where(Holding.asset_id == asset.asset_id)
        )).scalars().all()
        if not lots:
            continue
        quote = await get_quote(asset)
        fx_now = await get_rate_to_krw(db, asset.currency) or 0.0
        lot_dicts = [dict(quantity=float(l.quantity), purchase_price=float(l.purchase_price),
                          fee=float(l.fee or 0)) for l in lots]
        agg = aggregate_position(lot_dicts, current_price=quote.price, fx_now=fx_now)
        total_value += agg["value_krw"]
        positions.append({
            "asset_id": asset.asset_id, "ticker": asset.ticker, "name": asset.name,
            "market": asset.market, "currency": asset.currency,
            "current_price": quote.price, "price_status": quote.status, **agg,
        })

    # 현금: 통화별 KRW 환산. 매수·매도와 연동하지 않음(독립 관리).
    cash_rows = (await db.execute(select(CashBalance))).scalars().all()
    cash = []
    total_cash = 0.0
    for c in cash_rows:
        fx = await get_rate_to_krw(db, c.currency) or 0.0
        value_krw = float(c.amount) * fx
        total_cash += value_krw
        total_value += value_krw
        cash.append({"id": c.id, "currency": c.currency, "amount": float(c.amount),
                     "label": c.label, "value_krw": value_krw})

    # 비중은 종목+현금 전체(total_value) 기준.
    for p in positions:
        p["weight_pct"] = (p["value_krw"] / total_value * 100) if total_value else 0
    for c in cash:
        c["weight_pct"] = (c["value_krw"] / total_value * 100) if total_value else 0

    total_cost = sum(p["cost_krw"] for p in positions)
    positions_value = total_value - total_cash   # 종목 평가액 합(현금 제외)
    return {
        "positions": positions,
        "cash": cash,
        "summary": {
            "total_value_krw": total_value,
            "total_cost_krw": total_cost,
            "total_profit_loss_krw": positions_value - total_cost,
            "total_profit_loss_pct": ((positions_value - total_cost) / total_cost * 100) if total_cost else 0,
            "total_cash_krw": total_cash,
        },
    }
```

- [ ] **Step 2: import·전체 스위트 회귀 확인**

Run: `.venv/bin/python -c "from app.services.portfolio.portfolio_service import get_portfolio, aggregate_position; print('ok')"` → `ok`
Run: `.venv/bin/pytest -q` → 모든 테스트 PASS(+ DB 테스트 skip), 에러 없음.

- [ ] **Step 3: Commit**
```bash
git add app/services/portfolio/portfolio_service.py
git commit -m "feat: include cash in portfolio totals and weights; native aggregation"
```

---

## Task 6: holdings 라우터 — fx 자동채움 제거 + with-asset 추가

**Files:**
- Modify: `app/routers/holdings.py`

- [ ] **Step 1: app/routers/holdings.py 전체 교체**

```python
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Holding, Asset
from app.schemas.holding import HoldingCreate, HoldingWithAssetCreate, HoldingUpdate, HoldingOut

router = APIRouter(prefix="/api/holdings", tags=["holdings"])


@router.post("", response_model=HoldingOut)
async def create_holding(body: HoldingCreate, db: AsyncSession = Depends(get_db)):
    """기존 자산(asset_id)에 보유 lot 추가(분할매수)."""
    h = Holding(**body.model_dump())
    db.add(h)
    await db.commit()
    await db.refresh(h)
    return h


@router.post("/with-asset", response_model=HoldingOut)
async def create_with_asset(body: HoldingWithAssetCreate, db: AsyncSession = Depends(get_db)):
    """자산 upsert((ticker, market) 기준) + 보유 생성을 한 번에 처리."""
    asset = (await db.execute(
        select(Asset).where(Asset.ticker == body.ticker, Asset.market == body.market)
    )).scalar_one_or_none()
    if asset is None:
        asset = Asset(
            ticker=body.ticker, name=body.name, asset_type=body.asset_type, market=body.market,
            currency=body.currency, data_source=body.data_source, fetch_symbol=body.fetch_symbol,
            name_en=body.name_en,
        )
        db.add(asset)
        await db.flush()   # asset_id 확보(커밋 전)
    h = Holding(
        asset_id=asset.asset_id, quantity=body.quantity, purchase_price=body.purchase_price,
        purchase_date=body.purchase_date, fee=body.fee, memo=body.memo,
    )
    db.add(h)
    await db.commit()
    await db.refresh(h)
    return h


@router.get("", response_model=list[HoldingOut])
async def list_holdings(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Holding))).scalars().all()


@router.put("/{holding_id}", response_model=HoldingOut)
async def update_holding(holding_id: int, body: HoldingUpdate, db: AsyncSession = Depends(get_db)):
    h = await db.get(Holding, holding_id)
    if h is None:
        raise HTTPException(404, "holding not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(h, k, v)
    await db.commit()
    await db.refresh(h)
    return h


@router.delete("/{holding_id}")
async def delete_holding(holding_id: int, db: AsyncSession = Depends(get_db)):
    h = await db.get(Holding, holding_id)
    if h is None:
        raise HTTPException(404, "holding not found")
    await db.delete(h)
    await db.commit()
    return {"deleted": holding_id}
```

- [ ] **Step 2: 라우트 등록 확인**

Run: `.venv/bin/python -c "from app.routers.holdings import router; print(sorted((r.path, tuple(sorted(r.methods))) for r in router.routes))"`
Expected: `/api/holdings`(GET, POST), `/api/holdings/with-asset`(POST), `/api/holdings/{holding_id}`(PUT, DELETE) 가 보임.

- [ ] **Step 3: Commit**
```bash
git add app/routers/holdings.py
git commit -m "feat: holdings with-asset endpoint; drop fx auto-fill"
```

---

## Task 7: cash 라우터

**Files:**
- Create: `app/routers/cash.py`

- [ ] **Step 1: app/routers/cash.py 생성**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import CashBalance
from app.schemas.cash import CashCreate, CashUpdate, CashOut

router = APIRouter(prefix="/api/cash", tags=["cash"])


@router.post("", response_model=CashOut)
async def create_cash(body: CashCreate, db: AsyncSession = Depends(get_db)):
    if body.amount < 0:
        raise HTTPException(422, "amount는 음수일 수 없습니다.")
    c = CashBalance(**body.model_dump())
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@router.get("", response_model=list[CashOut])
async def list_cash(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(CashBalance))).scalars().all()


@router.put("/{cash_id}", response_model=CashOut)
async def update_cash(cash_id: int, body: CashUpdate, db: AsyncSession = Depends(get_db)):
    c = await db.get(CashBalance, cash_id)
    if c is None:
        raise HTTPException(404, "cash not found")
    data = body.model_dump(exclude_unset=True)
    if "amount" in data and data["amount"] is not None and data["amount"] < 0:
        raise HTTPException(422, "amount는 음수일 수 없습니다.")
    for k, v in data.items():
        setattr(c, k, v)
    await db.commit()
    await db.refresh(c)
    return c


@router.delete("/{cash_id}")
async def delete_cash(cash_id: int, db: AsyncSession = Depends(get_db)):
    c = await db.get(CashBalance, cash_id)
    if c is None:
        raise HTTPException(404, "cash not found")
    await db.delete(c)
    await db.commit()
    return {"deleted": cash_id}
```

- [ ] **Step 2: 라우트 확인**

Run: `.venv/bin/python -c "from app.routers.cash import router; print(sorted((r.path, tuple(sorted(r.methods))) for r in router.routes))"`
Expected: `/api/cash`(GET, POST), `/api/cash/{cash_id}`(PUT, DELETE).

- [ ] **Step 3: Commit**
```bash
git add app/routers/cash.py
git commit -m "feat: cash CRUD router"
```

---

## Task 8: main.py — cash 라우터 등록

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: import 줄 수정**

```python
from app.routers import assets, holdings, portfolio, fx, settings as settings_router, cash
```

- [ ] **Step 2: 라우터 등록 줄 수정**

```python
for r in (assets.router, holdings.router, portfolio.router, fx.router, settings_router.router, cash.router):
    app.include_router(r)
```

- [ ] **Step 3: 앱 import + 라우트 수 확인**

Run: `.venv/bin/python -c "from app.main import app; ps=sorted({r.path for r in app.routes}); print('/api/cash' in ps and '/api/holdings/with-asset' in ps)"` → `True`

- [ ] **Step 4: Commit**
```bash
git add app/main.py
git commit -m "feat: register cash router"
```

---

## Task 9: 개발 DB 마이그레이션 (holdings 재생성) — 수동/개발 전용

**Files:** 없음(런타임 DB 작업)

`ensure_schema()`는 생성 전용이라 기존 `invest.holdings`의 컬럼 변경(purchase_fx_rate 제거, purchase_date nullable)을 적용하지 못한다. 현재 holdings는 비어 있으므로 테이블을 drop 후 앱 부팅으로 재생성한다. `cash_balances`는 신규라 자동 생성된다.

- [ ] **Step 1: 개발 DB에서 holdings drop (데이터 없음 확인 후)**

```bash
.venv/bin/python - <<'PY'
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect(host="100.114.126.67", port=5432, user="ai_agent",
                              password="mook123!", database="agent_db")
    n = await c.fetchval("SELECT count(*) FROM invest.holdings")
    print("holdings rows:", n)
    assert n == 0, "holdings에 데이터가 있습니다 — 임의 삭제 금지, 사용자 확인 필요"
    await c.execute("DROP TABLE IF EXISTS invest.holdings CASCADE")
    print("dropped invest.holdings")
    await c.close()
asyncio.run(main())
PY
```
DB 접속이 안 되거나 행이 0이 아니면 중단하고 사용자에게 보고(BLOCKED). 이 단계는 개발 DB에만 적용되며 단위 테스트와 무관하다.

- [ ] **Step 2: 앱 부팅으로 재생성 확인**

```bash
.venv/bin/uvicorn app.main:app --port 8150 --log-level warning &
sleep 0  # 백그라운드 기동; 아래 curl이 재시도
curl -s --retry 20 --retry-delay 1 --retry-connrefused http://127.0.0.1:8150/health; echo
```
그 후 새 구조 확인:
```bash
.venv/bin/python - <<'PY'
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect(host="100.114.126.67", port=5432, user="ai_agent",
                              password="mook123!", database="agent_db")
    cols = [r['column_name'] for r in await c.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='invest' AND table_name='holdings'")]
    has_cash = await c.fetchval("SELECT count(*) FROM information_schema.tables WHERE table_schema='invest' AND table_name='cash_balances'")
    print("holdings cols:", cols)
    print("purchase_fx_rate present?", "purchase_fx_rate" in cols, "| cash_balances exists?", bool(has_cash))
    await c.close()
asyncio.run(main())
PY
pkill -f "uvicorn app.main:app --port 8150"
```
Expected: holdings에 `purchase_fx_rate` 없음, `cash_balances` 존재. (DB 접속 불가 시 이 단계 skip하고 사용자에게 안내.)

- [ ] **Step 3:** (커밋 없음 — DB 작업)

---

## Task 10: 프론트엔드 api.ts — cash·with-asset·타입

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: api 객체에 메서드 추가**

`export const api = { ... }` 안, 기존 `refresh:` 줄 다음에 추가:
```ts
  createHoldingWithAsset: (h: any) =>
    j("/api/holdings/with-asset", { method: "POST", body: JSON.stringify(h) }),
  listCash: () => j<any[]>("/api/cash"),
  createCash: (c: any) => j("/api/cash", { method: "POST", body: JSON.stringify(c) }),
  updateCash: (id: number, c: any) =>
    j(`/api/cash/${id}`, { method: "PUT", body: JSON.stringify(c) }),
  deleteCash: (id: number) => j(`/api/cash/${id}`, { method: "DELETE" }),
```

- [ ] **Step 2: 타입 보강 — Position·PortfolioOut 교체, CashPosition 추가**

`export interface Position { ... }` 와 `export interface PortfolioOut { ... }` 를 아래로 교체:
```ts
export interface Position {
  asset_id: number; ticker: string; name: string; market: string; currency: string;
  quantity: number; avg_price: number; current_price: number;
  cost_native: number; value_native: number; profit_loss_native: number;
  cost_krw: number; value_krw: number; profit_loss_krw: number; profit_loss_pct: number;
  weight_pct: number; price_status: string;
}
export interface CashPosition {
  id: number; currency: string; amount: number; label: string | null;
  value_krw: number; weight_pct: number;
}
export interface PortfolioOut {
  positions: Position[];
  cash: CashPosition[];
  summary: { total_value_krw: number; total_cost_krw: number;
             total_profit_loss_krw: number; total_profit_loss_pct: number; total_cash_krw: number };
}
```

- [ ] **Step 3: 빌드 확인** → Run: `cd frontend && npm run build 2>&1 | tail -2` → 빌드 성공.

- [ ] **Step 4: Commit**
```bash
git add frontend/src/api.ts
git commit -m "feat(frontend): cash and with-asset api + types"
```

---

## Task 11: 보유종목 통합 폼 (Holdings.tsx)

**Files:**
- Modify: `frontend/src/pages/Holdings.tsx`

- [ ] **Step 1: frontend/src/pages/Holdings.tsx 전체 교체**

```tsx
import { useEffect, useState } from "react";
import { api } from "../api";
import type { ResolveResponse } from "../api";

const MARKETS = ["US", "KR", "JP", "CRYPTO"];
const ASSET_TYPES = [
  { code: "", label: "자동 감지" }, { code: "stock", label: "주식" },
  { code: "etf", label: "ETF" }, { code: "bond", label: "채권 (수동가격)" },
  { code: "commodity", label: "원자재" }, { code: "crypto", label: "가상자산" },
];

export default function Holdings() {
  const [assets, setAssets] = useState<any[]>([]);
  const [holdings, setHoldings] = useState<any[]>([]);
  // 신규 등록(통합) 입력
  const [ticker, setTicker] = useState(""); const [market, setMarket] = useState("US");
  const [assetType, setAssetType] = useState("");
  const [preview, setPreview] = useState<ResolveResponse | null>(null);
  const [lot, setLot] = useState<any>({ quantity: "", purchase_price: "", purchase_date: "", fee: "", memo: "" });
  // 기존 자산에 분할매수
  const [existForm, setExistForm] = useState<any>({ asset_id: "", quantity: "", purchase_price: "", purchase_date: "", fee: "", memo: "" });

  const load = async () => { setAssets(await api.listAssets()); setHoldings(await api.listHoldings()); };
  useEffect(() => { load(); }, []);

  const doResolve = async () => setPreview(await api.resolve(ticker, market, assetType || undefined));

  const addNew = async () => {
    if (!preview?.asset) return;
    await api.createHoldingWithAsset({
      ...preview.asset,
      quantity: Number(lot.quantity), purchase_price: Number(lot.purchase_price),
      purchase_date: lot.purchase_date || null, fee: Number(lot.fee || 0), memo: lot.memo || null,
    });
    setPreview(null); setTicker(""); setLot({ quantity: "", purchase_price: "", purchase_date: "", fee: "", memo: "" });
    await load();
  };

  const addExisting = async () => {
    await api.createHolding({
      asset_id: Number(existForm.asset_id), quantity: Number(existForm.quantity),
      purchase_price: Number(existForm.purchase_price), purchase_date: existForm.purchase_date || null,
      fee: Number(existForm.fee || 0), memo: existForm.memo || null,
    });
    setExistForm({ asset_id: "", quantity: "", purchase_price: "", purchase_date: "", fee: "", memo: "" });
    await load();
  };

  const remove = async (id: number) => { await api.deleteHolding(id); await load(); };

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold">보유종목 추가</h1>

      {/* 신규: 조회 → 등록 한 흐름 */}
      <section className="space-y-2">
        <div className="flex gap-2 items-center flex-wrap">
          <input className="border rounded px-2 py-1" placeholder="티커 (AAPL, 005930, BTC, GC=F)"
            value={ticker} onChange={(e) => setTicker(e.target.value)} />
          <select className="border rounded px-2 py-1" value={market} onChange={(e) => setMarket(e.target.value)}>
            {MARKETS.map((m) => <option key={m}>{m}</option>)}
          </select>
          <select className="border rounded px-2 py-1" value={assetType} onChange={(e) => setAssetType(e.target.value)}>
            {ASSET_TYPES.map((t) => <option key={t.code} value={t.code}>{t.label}</option>)}
          </select>
          <button onClick={doResolve} className="px-3 py-1 rounded bg-gray-800 text-white">조회</button>
        </div>

        {preview && (preview.ok && preview.asset ? (
          <div className="rounded border p-3 bg-green-50 space-y-2">
            <div><b>{preview.asset.name}</b> · {preview.asset.currency} · {preview.asset.asset_type} · 현재가 {preview.asset.current_price ?? "—"}</div>
            <div className="flex gap-2 flex-wrap">
              <input className="border rounded px-2 py-1 w-24" placeholder="수량"
                value={lot.quantity} onChange={(e) => setLot({ ...lot, quantity: e.target.value })} />
              <input className="border rounded px-2 py-1 w-32" placeholder={`매입단가 (${preview.asset.currency})`}
                value={lot.purchase_price} onChange={(e) => setLot({ ...lot, purchase_price: e.target.value })} />
              <input type="date" className="border rounded px-2 py-1" title="매입일(선택)"
                value={lot.purchase_date} onChange={(e) => setLot({ ...lot, purchase_date: e.target.value })} />
              <input className="border rounded px-2 py-1 w-24" placeholder="수수료"
                value={lot.fee} onChange={(e) => setLot({ ...lot, fee: e.target.value })} />
              <input className="border rounded px-2 py-1" placeholder="메모"
                value={lot.memo} onChange={(e) => setLot({ ...lot, memo: e.target.value })} />
              <button onClick={addNew} className="px-3 py-1 rounded bg-blue-600 text-white">보유 추가</button>
            </div>
          </div>
        ) : (
          <div className="rounded border p-3 bg-amber-50">
            <div>조회 실패 (시도: {preview.tried.join(", ")})</div>
            <div className="text-sm text-gray-600">{preview.suggestion}</div>
          </div>
        ))}
      </section>

      {/* 기존 자산에 분할매수 */}
      <section className="space-y-2">
        <h2 className="font-semibold">기존 자산에 추가 매수</h2>
        <div className="flex gap-2 flex-wrap">
          <select className="border rounded px-2 py-1" value={existForm.asset_id}
            onChange={(e) => setExistForm({ ...existForm, asset_id: e.target.value })}>
            <option value="">자산 선택</option>
            {assets.map((a) => <option key={a.asset_id} value={a.asset_id}>{a.ticker}·{a.market} {a.name}</option>)}
          </select>
          <input className="border rounded px-2 py-1 w-24" placeholder="수량"
            value={existForm.quantity} onChange={(e) => setExistForm({ ...existForm, quantity: e.target.value })} />
          <input className="border rounded px-2 py-1 w-32" placeholder="매입단가"
            value={existForm.purchase_price} onChange={(e) => setExistForm({ ...existForm, purchase_price: e.target.value })} />
          <input type="date" className="border rounded px-2 py-1" title="매입일(선택)"
            value={existForm.purchase_date} onChange={(e) => setExistForm({ ...existForm, purchase_date: e.target.value })} />
          <input className="border rounded px-2 py-1 w-24" placeholder="수수료"
            value={existForm.fee} onChange={(e) => setExistForm({ ...existForm, fee: e.target.value })} />
          <button onClick={addExisting} className="px-3 py-1 rounded bg-blue-600 text-white">추가</button>
        </div>
      </section>

      {/* 보유 목록 */}
      <section>
        <h2 className="font-semibold">보유 목록</h2>
        <table className="w-full text-sm mt-2">
          <thead><tr className="border-b text-left text-gray-500">
            <th className="py-2">자산ID</th><th>매입일</th><th>수량</th><th>단가</th><th></th>
          </tr></thead>
          <tbody>
            {holdings.map((h) => (
              <tr key={h.holding_id} className="border-b">
                <td className="py-2">{h.asset_id}</td><td>{h.purchase_date ?? "—"}</td>
                <td>{h.quantity}</td><td>{h.purchase_price}</td>
                <td><button onClick={() => remove(h.holding_id)} className="text-red-600">삭제</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: 빌드 확인** → Run: `cd frontend && npm run build 2>&1 | tail -2` → 성공.

- [ ] **Step 3: Commit**
```bash
git add frontend/src/pages/Holdings.tsx
git commit -m "feat(frontend): integrated holding registration (resolve + add) and optional date"
```

---

## Task 12: 현금 화면 (Cash.tsx)

**Files:**
- Create: `frontend/src/pages/Cash.tsx`

- [ ] **Step 1: frontend/src/pages/Cash.tsx 생성**

```tsx
import { useEffect, useState } from "react";
import { api } from "../api";

const CURRENCIES = ["KRW", "USD", "JPY"];

export default function Cash() {
  const [rows, setRows] = useState<any[]>([]);
  const [form, setForm] = useState<any>({ currency: "KRW", amount: "", label: "", memo: "" });
  const load = async () => setRows(await api.listCash());
  useEffect(() => { load(); }, []);

  const add = async () => {
    await api.createCash({ currency: form.currency, amount: Number(form.amount),
      label: form.label || null, memo: form.memo || null });
    setForm({ currency: "KRW", amount: "", label: "", memo: "" });
    await load();
  };
  const remove = async (id: number) => { await api.deleteCash(id); await load(); };

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-xl font-bold">현금</h1>
      <div className="flex gap-2 flex-wrap items-center">
        <select className="border rounded px-2 py-1" value={form.currency}
          onChange={(e) => setForm({ ...form, currency: e.target.value })}>
          {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
        </select>
        <input className="border rounded px-2 py-1 w-40" placeholder="금액"
          value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        <input className="border rounded px-2 py-1" placeholder="라벨(예: 증권사 예수금)"
          value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
        <button onClick={add} className="px-3 py-1 rounded bg-blue-600 text-white">추가</button>
      </div>

      <table className="w-full text-sm">
        <thead><tr className="border-b text-left text-gray-500">
          <th className="py-2">통화</th><th>금액</th><th>라벨</th><th></th>
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b">
              <td className="py-2">{r.currency}</td><td>{Number(r.amount).toLocaleString()}</td>
              <td>{r.label ?? "—"}</td>
              <td><button onClick={() => remove(r.id)} className="text-red-600">삭제</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Commit** (라우트 연결은 Task 14에서) — 빌드는 App에 연결 후 Task 14에서 확인.
```bash
git add frontend/src/pages/Cash.tsx
git commit -m "feat(frontend): cash management page"
```

---

## Task 13: 대시보드 현금 섹션 (Dashboard.tsx)

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: 요약 카드 영역에 현금 카드 추가**

`grid grid-cols-2 gap-4` 를 `grid grid-cols-3 gap-4` 로 바꾸고, 총손익 카드 `</div>` 다음(그 grid 닫기 전)에 현금 카드 추가:
```tsx
        <div className="rounded border p-4">
          <div className="text-sm text-gray-500">현금 (KRW)</div>
          <div className="text-2xl font-semibold">₩{krw(s.total_cash_krw)}</div>
        </div>
```

- [ ] **Step 2: 포지션 테이블 다음에 현금 목록 섹션 추가**

`</table>` (포지션 테이블 닫기) 다음, 컴포넌트 최상위 `</div>` 전에 추가:
```tsx
      {data.cash.length > 0 && (
        <div>
          <h2 className="font-semibold mb-2">현금</h2>
          <table className="w-full text-sm border-collapse">
            <thead><tr className="border-b text-left text-gray-500">
              <th className="py-2">통화</th><th>금액</th><th>라벨</th><th>평가액(KRW)</th><th>비중</th>
            </tr></thead>
            <tbody>
              {data.cash.map((c) => (
                <tr key={c.id} className="border-b">
                  <td className="py-2">{c.currency}</td><td>{c.amount.toLocaleString()}</td>
                  <td>{c.label ?? "—"}</td><td>₩{krw(c.value_krw)}</td><td>{c.weight_pct.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
```

- [ ] **Step 2b: 빌드 확인** → Run: `cd frontend && npm run build 2>&1 | tail -2` → 성공(타입상 `data.cash`, `total_cash_krw` 인식).

- [ ] **Step 3: Commit**
```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(frontend): cash summary card and cash list on dashboard"
```

---

## Task 14: 라우팅·네비 (App.tsx)

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: import + 라우트 + 네비 추가**

`import Holdings from "./pages/Holdings";` 다음 줄에:
```tsx
import Cash from "./pages/Cash";
```
네비의 `<Link to="/holdings">보유</Link>` 다음에:
```tsx
        <Link to="/cash">현금</Link>
```
`<Route path="/holdings" element={<Holdings />} />` 다음에:
```tsx
        <Route path="/cash" element={<Cash />} />
```

- [ ] **Step 2: 빌드 + 라우트 동작 확인** → Run: `cd frontend && npm run build 2>&1 | tail -2` → 성공.

- [ ] **Step 3: Commit**
```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): cash route and nav"
```

---

## Task 15: 최종 검증 (단위 + 빌드, 선택적 실DB 스모크)

**Files:** 없음

- [ ] **Step 1: 백엔드 단위 스위트**
Run: `.venv/bin/pytest -q` → 모든 PASS(+ DB 테스트 skip), 에러 없음.

- [ ] **Step 2: 앱 import + 라우트**
Run: `.venv/bin/python -c "from app.main import app; print(len(app.routes), 'routes')"` → 정상(현금 4 + with-asset 1 추가).

- [ ] **Step 3: 프론트 빌드**
Run: `cd frontend && npm run build 2>&1 | tail -2` → 성공.

- [ ] **Step 4: (선택, DB 접속 시) 실DB 엔드투엔드 스모크**
앱을 띄우고(`uvicorn ... --port 8151`), curl로: `POST /api/cash`(KRW 1000000) → `POST /api/holdings/with-asset`(AAPL/US, qty 10, price 150, 날짜 생략) → `GET /api/portfolio` 에서 positions·cash·summary.total_cash_krw 확인. 검증 후 테스트 행 정리(`TRUNCATE invest.cash_balances, invest.holdings, invest.assets ... RESTART IDENTITY`). DB 접속 불가 시 skip하고 보고.

- [ ] **Step 5:** (커밋 없음)

---

## Self-Review (spec 대비 커버리지)

- spec §3 환율·손익 단순화(fx_rate 제거, 자산통화+현재환율) → Task 1·2·5. ✅
- spec §3 purchase_date nullable → Task 1(model/schema) + Task 11(UI 선택). ✅
- spec §4 현금 자산군(테이블·평가·통합·API) → Task 3·4·5·7. ✅
- spec §5 보유종목 등록 통합(with-asset + 단일 폼) → Task 6·11. ✅
- spec §6 영향 컴포넌트 전부 → Task 1~14. ✅
- spec §3 마이그레이션(holdings drop·재부트스트랩) → Task 9. ✅
- spec §7 테스트(손익·집계·회귀) → Task 2 + Task 15. (현금 KRW 환산·with-asset은 DB 통합 경로라 단위테스트는 aggregate 중심, 실DB 스모크는 Task 15 Step 4.) ✅
- spec §8 오류처리(현금 음수 422, with-asset 중복 upsert) → Task 7·6. ✅

타입 일관성: `aggregate_position` 반환 키(cost_native/value_native/profit_loss_native/cost_krw/value_krw/profit_loss_krw/profit_loss_pct/quantity/avg_price)가 Position 스키마·get_portfolio·api.ts·Dashboard에서 동일하게 사용됨. PortfolioOut에 `cash`·`summary.total_cash_krw` 추가가 스키마·서비스·TS 타입·Dashboard에서 일치. with-asset 입력 필드가 HoldingWithAssetCreate와 프론트 `{...preview.asset, quantity, ...}` 페이로드에서 일치(ResolvedAssetOut가 ticker/name/asset_type/market/currency/data_source/fetch_symbol/name_en 포함).
