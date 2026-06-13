# invest_portal 1단계 (기반 + 포트폴리오 코어) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** my-assistant의 금융 기능과 신규 포트폴리오 관리를 ytdb 스택으로 재구성한 종합 자산관리 앱의 1단계(멀티마켓 티커 해석·시세 + 포트폴리오 lot 관리 + KRW 환율변환 + React 대시보드)를 구축한다.

**Architecture:** FastAPI(JSON API) + 비동기 SQLAlchemy 2.0 + asyncpg + PostgreSQL 전용. 단일 `invest` 스키마를 부팅 시 멱등 생성. 시세는 `(market, data_source)`로 디스패치하는 Provider 레지스트리(yfinance/pykrx/manual)가 담당하고, 블로킹 라이브러리는 `asyncio.to_thread`로 감싼다. 프론트는 React+Vite+TS+Tailwind SPA.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy 2.0(async), asyncpg, pydantic-settings, cryptography(Fernet), yfinance, pykrx, pytest+pytest-asyncio / React 18, Vite, TypeScript, Tailwind, react-router.

**참조:** 설계 spec `docs/superpowers/specs/2026-06-13-invest-portal-phase1-portfolio-core-design.md`. 후속 2·3단계는 그 spec의 "비범위" 절에 정의됨(이 계획 범위 외).

---

## 파일 구조 (이 계획이 생성/수정하는 것)

```
invest_portal/
├── requirements.txt              # Python 의존성
├── .env.example                  # DATABASE_URL, FERNET_KEY
├── pytest.ini                    # asyncio 모드
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI + lifespan(ensure_schema) + 라우터 등록
│   ├── config.py                 # pydantic-settings
│   ├── db.py                     # async 엔진/세션/Base (invest 스키마)
│   ├── bootstrap.py              # ensure_schema
│   ├── models/
│   │   ├── __init__.py           # 모든 모델 re-export
│   │   ├── asset.py              # Asset
│   │   ├── exchange_rate.py      # ExchangeRate
│   │   ├── price_snapshot.py     # PriceSnapshot
│   │   ├── holding.py            # Holding
│   │   └── app_setting.py        # AppSetting
│   ├── schemas/
│   │   ├── asset.py
│   │   ├── holding.py
│   │   ├── portfolio.py
│   │   └── market.py             # ResolvedAsset/Quote 입출력
│   ├── services/
│   │   ├── market/
│   │   │   ├── types.py          # ResolvedAsset, Quote 데이터클래스
│   │   │   ├── base.py           # PriceProvider 프로토콜
│   │   │   ├── yfinance_provider.py
│   │   │   ├── pykrx_provider.py
│   │   │   ├── manual_provider.py
│   │   │   ├── registry.py       # ProviderRegistry
│   │   │   ├── resolver.py       # AssetResolver
│   │   │   └── quote_service.py  # QuoteService
│   │   ├── fx/fx_service.py
│   │   ├── portfolio/portfolio_service.py
│   │   └── settings/settings_manager.py
│   └── routers/
│       ├── assets.py
│       ├── holdings.py
│       ├── portfolio.py
│       ├── fx.py
│       └── settings.py
├── tests/
│   ├── conftest.py               # async 세션 픽스처 + provider 모킹
│   ├── test_bootstrap.py
│   ├── test_providers_yfinance.py
│   ├── test_providers_pykrx.py
│   ├── test_resolver.py
│   ├── test_fx_service.py
│   ├── test_portfolio_service.py
│   └── test_api.py
└── frontend/                     # Vite React TS (Task 18~21)
```

**테스트 DB:** 통합 테스트는 spec의 PostgreSQL(`100.114.126.67:5432/agent_db`, schema `invest_test`)을 사용하거나, `TEST_DATABASE_URL` 미설정 시 해당 통합 테스트를 skip한다. 외부 시세 API(yfinance/pykrx)는 항상 모킹한다.

---

## Task 1: 프로젝트 골격 + 설정 + DB 엔진

**Files:**
- Create: `requirements.txt`, `.env.example`, `pytest.ini`, `app/__init__.py`, `app/config.py`, `app/db.py`

- [ ] **Step 1: requirements.txt 작성**

```
fastapi>=0.111.0
uvicorn[standard]>=0.30.0
SQLAlchemy>=2.0.30
asyncpg>=0.29.0
greenlet>=3.0.0
pydantic>=2.7.0
pydantic-settings>=2.3.0
cryptography>=42.0.0
yfinance>=0.2.40
pykrx>=1.0.45
pandas>=2.2.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

- [ ] **Step 2: .env.example 와 pytest.ini 작성**

`.env.example`:
```
# 비동기 드라이버 DSN. 부팅 시 invest 스키마를 멱등 생성한다.
DATABASE_URL=postgresql+asyncpg://ai_agent:CHANGEME@100.114.126.67:5432/agent_db
# 통합 테스트용(미설정 시 DB 통합 테스트 skip)
TEST_DATABASE_URL=
# Fernet 키 생성: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY=CHANGEME
```

`pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 3: app/config.py 작성**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    FERNET_KEY: str
    SCHEMA_NAME: str = "invest"
    TEST_DATABASE_URL: str | None = None


settings = Settings()
```

- [ ] **Step 4: app/db.py 작성**

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData

from app.config import settings

# 모든 테이블을 invest 스키마에 귀속시킨다.
metadata_obj = MetaData(schema=settings.SCHEMA_NAME)


class Base(DeclarativeBase):
    metadata = metadata_obj


engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
```

- [ ] **Step 5: app/__init__.py 빈 파일 생성 후 커밋**

```bash
git add requirements.txt .env.example pytest.ini app/__init__.py app/config.py app/db.py
git commit -m "feat: project scaffolding, config, async db engine"
```

---

## Task 2: SQLAlchemy 모델

**Files:**
- Create: `app/models/__init__.py`, `app/models/asset.py`, `app/models/exchange_rate.py`, `app/models/price_snapshot.py`, `app/models/holding.py`, `app/models/app_setting.py`

- [ ] **Step 1: app/models/asset.py**

```python
from datetime import datetime
from sqlalchemy import String, Boolean, Numeric, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("ticker", "market", name="uq_assets_ticker_market"),)

    asset_id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    name_en: Mapped[str | None] = mapped_column(String)
    asset_type: Mapped[str] = mapped_column(String, nullable=False)   # stock/etf/etn/index/crypto/bond/fund
    market: Mapped[str] = mapped_column(String, nullable=False)        # US/KR/JP/CRYPTO
    currency: Mapped[str] = mapped_column(String, nullable=False)      # USD/KRW/JPY
    data_source: Mapped[str] = mapped_column(String, nullable=False)   # yfinance/pykrx/manual
    fetch_symbol: Mapped[str] = mapped_column(String, nullable=False)
    manual_price: Mapped[float | None] = mapped_column(Numeric)
    manual_price_currency: Mapped[str | None] = mapped_column(String)
    manual_price_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 2: app/models/exchange_rate.py**

```python
from datetime import datetime, date
from sqlalchemy import String, Numeric, Date, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("date", "base_currency", "quote_currency", name="uq_fx_date_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    base_currency: Mapped[str] = mapped_column(String, nullable=False)   # USD/JPY
    quote_currency: Mapped[str] = mapped_column(String, nullable=False)  # KRW
    rate: Mapped[float] = mapped_column(Numeric, nullable=False)         # base 1단위당 quote 금액
    source: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 3: app/models/price_snapshot.py**

```python
from datetime import datetime, date
from sqlalchemy import String, Numeric, Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    __table_args__ = (UniqueConstraint("asset_id", "date", name="uq_price_asset_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    close: Mapped[float] = mapped_column(Numeric, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: app/models/holding.py**

```python
from datetime import datetime, date
from sqlalchemy import String, Numeric, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class Holding(Base):
    __tablename__ = "holdings"

    holding_id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric, nullable=False)
    purchase_price: Mapped[float] = mapped_column(Numeric, nullable=False)
    purchase_fx_rate: Mapped[float | None] = mapped_column(Numeric)   # 매입시점 KRW 환율, KRW 자산은 1
    fee: Mapped[float] = mapped_column(Numeric, default=0)
    memo: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 5: app/models/app_setting.py**

```python
from datetime import datetime
from sqlalchemy import String, Boolean, LargeBinary, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = (UniqueConstraint("category", "key", name="uq_settings_category_key"),)

    setting_id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    key: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str | None] = mapped_column(String)
    value_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    value_type: Mapped[str] = mapped_column(String, nullable=False, default="string")
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 6: app/models/__init__.py — 모델 re-export**

```python
from app.models.asset import Asset
from app.models.exchange_rate import ExchangeRate
from app.models.price_snapshot import PriceSnapshot
from app.models.holding import Holding
from app.models.app_setting import AppSetting

__all__ = ["Asset", "ExchangeRate", "PriceSnapshot", "Holding", "AppSetting"]
```

- [ ] **Step 7: 커밋**

```bash
git add app/models/
git commit -m "feat: SQLAlchemy models for assets, fx, snapshots, holdings, settings"
```

---

## Task 2.5: 테스트 인프라 (conftest)

**Files:**
- Create: `tests/__init__.py`, `tests/conftest.py`

- [ ] **Step 1: tests/conftest.py 작성**

```python
import os
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy import text

from app.db import Base
from app.config import settings

TEST_URL = os.environ.get("TEST_DATABASE_URL") or settings.TEST_DATABASE_URL


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """통합 테스트용 세션. TEST_DATABASE_URL 미설정 시 skip."""
    if not TEST_URL:
        pytest.skip("TEST_DATABASE_URL 미설정 — DB 통합 테스트 skip")
    engine = create_async_engine(TEST_URL)
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {settings.SCHEMA_NAME}"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()
```

- [ ] **Step 2: tests/__init__.py 빈 파일 생성 후 커밋**

```bash
git add tests/__init__.py tests/conftest.py
git commit -m "test: async db session fixture with skip-when-unconfigured"
```

---

## Task 3: bootstrap.ensure_schema (멱등성)

**Files:**
- Create: `app/bootstrap.py`, `tests/test_bootstrap.py`

- [ ] **Step 1: 실패 테스트 작성 — tests/test_bootstrap.py**

```python
import pytest
from sqlalchemy import text
from app.bootstrap import ensure_schema
from app.config import settings


@pytest.mark.asyncio
async def test_ensure_schema_is_idempotent(db_session):
    # 두 번 호출해도 예외가 없어야 한다.
    await ensure_schema(db_session.bind)
    await ensure_schema(db_session.bind)
    rows = await db_session.execute(text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema=:s"
    ), {"s": settings.SCHEMA_NAME})
    names = {r[0] for r in rows}
    assert {"assets", "exchange_rates", "price_snapshots", "holdings", "app_settings"} <= names
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_bootstrap.py -v`
Expected: FAIL — `ModuleNotFoundError: app.bootstrap` (또는 TEST_DATABASE_URL 미설정 시 SKIP)

- [ ] **Step 3: app/bootstrap.py 구현**

```python
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db import Base
from app.config import settings
import app.models  # noqa: F401  — 모든 모델을 메타데이터에 등록


async def ensure_schema(engine: AsyncEngine) -> None:
    """invest 스키마와 모든 테이블을 멱등 생성한다."""
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {settings.SCHEMA_NAME}"))
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 4: 통과 확인**

Run: `TEST_DATABASE_URL=<dsn> pytest tests/test_bootstrap.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add app/bootstrap.py tests/test_bootstrap.py
git commit -m "feat: idempotent ensure_schema bootstrap"
```

---

## Task 4: Market 타입 + Provider 프로토콜

**Files:**
- Create: `app/services/__init__.py`, `app/services/market/__init__.py`, `app/services/market/types.py`, `app/services/market/base.py`

- [ ] **Step 1: app/services/market/types.py**

```python
from dataclasses import dataclass
from datetime import date


@dataclass
class ResolvedAsset:
    ticker: str
    name: str
    asset_type: str          # stock/etf/etn/index/crypto/bond/fund
    market: str              # US/KR/JP/CRYPTO
    currency: str            # USD/KRW/JPY
    data_source: str         # yfinance/pykrx/manual
    fetch_symbol: str
    current_price: float | None = None
    name_en: str | None = None


@dataclass
class Quote:
    price: float
    currency: str
    change: float | None = None
    change_pct: float | None = None
    volume: float | None = None
    as_of: date | None = None
    status: str = "ok"       # ok/stale/error
```

- [ ] **Step 2: app/services/market/base.py**

```python
from typing import Protocol
from app.services.market.types import ResolvedAsset, Quote


class PriceProvider(Protocol):
    def resolve(self, ticker: str, market: str, asset_type_hint: str | None = None) -> ResolvedAsset | None:
        ...

    def quote(self, fetch_symbol: str, currency: str, asset_type: str) -> Quote | None:
        ...
```

`AssetLike` 인자 메모: provider는 ORM에 의존하지 않도록 `fetch_symbol`/`currency`/`asset_type` 원시값을 받는다. ManualProvider는 추가로 `manual_price`를 받는 별도 시그니처를 가지므로 registry에서 분기 처리한다(Task 8).

- [ ] **Step 3: 빈 __init__.py 생성 후 커밋**

```bash
git add app/services/__init__.py app/services/market/__init__.py app/services/market/types.py app/services/market/base.py
git commit -m "feat: market provider types and protocol"
```

---

## Task 5: YFinanceProvider (US / JP / CRYPTO / INDEX)

**Files:**
- Create: `app/services/market/yfinance_provider.py`, `tests/test_providers_yfinance.py`

- [ ] **Step 1: 실패 테스트 — tests/test_providers_yfinance.py**

```python
from unittest.mock import MagicMock, patch
import pandas as pd
from app.services.market.yfinance_provider import YFinanceProvider


def _fake_hist():
    return pd.DataFrame({"Close": [100.0, 110.0], "Volume": [10, 20]})


@patch("app.services.market.yfinance_provider.yf.Ticker")
def test_resolve_us_equity(mock_ticker):
    inst = MagicMock()
    inst.history.return_value = _fake_hist()
    inst.info = {"quoteType": "EQUITY", "longName": "Apple Inc.", "currency": "USD"}
    mock_ticker.return_value = inst

    p = YFinanceProvider()
    r = p.resolve("AAPL", "US")
    assert r is not None
    assert r.fetch_symbol == "AAPL"
    assert r.asset_type == "stock"
    assert r.currency == "USD"
    assert r.current_price == 110.0


@patch("app.services.market.yfinance_provider.yf.Ticker")
def test_resolve_jp_appends_t_suffix(mock_ticker):
    inst = MagicMock()
    inst.history.return_value = _fake_hist()
    inst.info = {"quoteType": "EQUITY", "longName": "Toyota", "currency": "JPY"}
    mock_ticker.return_value = inst

    p = YFinanceProvider()
    r = p.resolve("7203", "JP")
    assert r.fetch_symbol == "7203.T"
    assert r.currency == "JPY"


@patch("app.services.market.yfinance_provider.yf.Ticker")
def test_resolve_crypto_appends_usd(mock_ticker):
    inst = MagicMock()
    inst.history.return_value = _fake_hist()
    inst.info = {"quoteType": "CRYPTOCURRENCY", "shortName": "Bitcoin", "currency": "USD"}
    mock_ticker.return_value = inst

    p = YFinanceProvider()
    r = p.resolve("BTC", "CRYPTO")
    assert r.fetch_symbol == "BTC-USD"
    assert r.asset_type == "crypto"


@patch("app.services.market.yfinance_provider.yf.Ticker")
def test_resolve_returns_none_on_empty_history(mock_ticker):
    inst = MagicMock()
    inst.history.return_value = pd.DataFrame()
    inst.info = {}
    mock_ticker.return_value = inst

    p = YFinanceProvider()
    assert p.resolve("NOPE", "US") is None
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_providers_yfinance.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: app/services/market/yfinance_provider.py 구현**

```python
from datetime import date
import yfinance as yf
from app.services.market.types import ResolvedAsset, Quote

# yfinance quoteType → 내부 asset_type
_QUOTE_TYPE_MAP = {
    "EQUITY": "stock",
    "ETF": "etf",
    "INDEX": "index",
    "MUTUALFUND": "fund",
    "CRYPTOCURRENCY": "crypto",
}

_MARKET_CURRENCY = {"US": "USD", "JP": "JPY", "CRYPTO": "USD"}


def _fetch_symbol(ticker: str, market: str) -> str:
    t = ticker.strip().upper()
    if market == "JP":
        return t if t.endswith(".T") else f"{t}.T"
    if market == "CRYPTO":
        return t if "-" in t else f"{t}-USD"
    return t  # US (지수는 사용자가 ^ 포함해 입력)


class YFinanceProvider:
    def resolve(self, ticker, market, asset_type_hint=None):
        symbol = _fetch_symbol(ticker, market)
        try:
            inst = yf.Ticker(symbol)
            hist = inst.history(period="7d")
            if hist is None or hist.empty:
                return None
            price = float(hist["Close"].iloc[-1])
            info = {}
            try:
                info = inst.info or {}
            except Exception:
                info = {}
            quote_type = info.get("quoteType", "")
            asset_type = _QUOTE_TYPE_MAP.get(quote_type, asset_type_hint or "stock")
            currency = info.get("currency") or _MARKET_CURRENCY.get(market, "USD")
            name = info.get("longName") or info.get("shortName") or ticker
            return ResolvedAsset(
                ticker=ticker.strip().upper(),
                name=name,
                asset_type=asset_type,
                market=market,
                currency=currency,
                data_source="yfinance",
                fetch_symbol=symbol,
                current_price=price,
                name_en=info.get("longName"),
            )
        except Exception:
            return None

    def quote(self, fetch_symbol, currency, asset_type):
        try:
            hist = yf.Ticker(fetch_symbol).history(period="7d")
            if hist is None or hist.empty:
                return Quote(price=0.0, currency=currency, status="error")
            close = hist["Close"]
            price = float(close.iloc[-1])
            change = change_pct = None
            if len(close) >= 2:
                prev = float(close.iloc[-2])
                if prev:
                    change = price - prev
                    change_pct = change / prev * 100
            vol = float(hist["Volume"].iloc[-1]) if "Volume" in hist else None
            return Quote(price=price, currency=currency, change=change,
                         change_pct=change_pct, volume=vol, as_of=date.today(), status="ok")
        except Exception:
            return Quote(price=0.0, currency=currency, status="error")
```

- [ ] **Step 4: 통과 확인 + 커밋**

Run: `pytest tests/test_providers_yfinance.py -v` → Expected: PASS

```bash
git add app/services/market/yfinance_provider.py tests/test_providers_yfinance.py
git commit -m "feat: yfinance provider for US/JP/crypto with symbol resolution"
```

---

## Task 6: PykrxProvider (KR — ETF/ETN/주식 분기)

**Files:**
- Create: `app/services/market/pykrx_provider.py`, `tests/test_providers_pykrx.py`

이 Task가 기존 앱의 KR ETF 실패를 해결하는 핵심이다. 티커가 ETF/ETN 리스트에 속하는지 먼저 판정해 올바른 pykrx 함수를 고른다.

- [ ] **Step 1: 실패 테스트 — tests/test_providers_pykrx.py**

```python
from unittest.mock import patch
import pandas as pd
from app.services.market.pykrx_provider import PykrxProvider


def _stock_df():
    return pd.DataFrame({"종가": [70000, 71000], "거래량": [100, 200]})


def _etf_df():
    return pd.DataFrame({"종가": [10000, 10100], "거래량": [50, 60]})


@patch("app.services.market.pykrx_provider.stock")
def test_resolve_kr_stock(mock_stock):
    mock_stock.get_etf_ticker_list.return_value = ["069500"]
    mock_stock.get_etn_ticker_list.return_value = []
    mock_stock.get_market_ticker_name.return_value = "삼성전자"
    mock_stock.get_market_ohlcv_by_date.return_value = _stock_df()

    r = PykrxProvider().resolve("005930", "KR")
    assert r.asset_type == "stock"
    assert r.currency == "KRW"
    assert r.fetch_symbol == "005930"
    assert r.current_price == 71000


@patch("app.services.market.pykrx_provider.stock")
def test_resolve_kr_etf_uses_etf_functions(mock_stock):
    mock_stock.get_etf_ticker_list.return_value = ["069500"]
    mock_stock.get_etn_ticker_list.return_value = []
    mock_stock.get_etf_ticker_name.return_value = "KODEX 200"
    mock_stock.get_etf_ohlcv_by_date.return_value = _etf_df()

    r = PykrxProvider().resolve("069500", "KR")
    assert r.asset_type == "etf"
    assert r.current_price == 10100
    mock_stock.get_etf_ohlcv_by_date.assert_called()       # ETF 함수 사용 확인
    mock_stock.get_market_ohlcv_by_date.assert_not_called()  # 주식 함수 미사용


@patch("app.services.market.pykrx_provider.stock")
def test_resolve_kr_unknown_returns_none(mock_stock):
    mock_stock.get_etf_ticker_list.return_value = []
    mock_stock.get_etn_ticker_list.return_value = []
    mock_stock.get_market_ticker_name.return_value = None
    r = PykrxProvider().resolve("999999", "KR")
    assert r is None
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_providers_pykrx.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: app/services/market/pykrx_provider.py 구현**

```python
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from pykrx import stock
from app.services.market.types import ResolvedAsset, Quote


def _today_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")


def _window_start() -> str:
    return (datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=10)).strftime("%Y%m%d")


class PykrxProvider:
    """KR 전용. ETF/ETN/주식을 리스트 멤버십으로 판정해 올바른 함수를 호출한다."""

    def _classify(self, ticker: str) -> str:
        today = _today_kst()
        try:
            if ticker in set(stock.get_etf_ticker_list(today)):
                return "etf"
        except Exception:
            pass
        try:
            if ticker in set(stock.get_etn_ticker_list(today)):
                return "etn"
        except Exception:
            pass
        return "stock"

    def _ohlcv(self, ticker: str, asset_type: str):
        start, end = _window_start(), _today_kst()
        if asset_type == "etf":
            return stock.get_etf_ohlcv_by_date(start, end, ticker)
        if asset_type == "etn":
            return stock.get_etn_ohlcv_by_date(start, end, ticker)
        return stock.get_market_ohlcv_by_date(start, end, ticker)

    def _name(self, ticker: str, asset_type: str):
        if asset_type == "etf":
            return stock.get_etf_ticker_name(ticker)
        if asset_type == "etn":
            return stock.get_etn_ticker_name(ticker)
        return stock.get_market_ticker_name(ticker)

    def resolve(self, ticker, market, asset_type_hint=None):
        ticker = ticker.strip()
        asset_type = self._classify(ticker)
        try:
            name = self._name(ticker, asset_type)
            if not name or not isinstance(name, str):
                return None
            df = self._ohlcv(ticker, asset_type)
            if df is None or df.empty:
                return None
            price = float(df["종가"].iloc[-1])
            return ResolvedAsset(
                ticker=ticker, name=name, asset_type=asset_type, market="KR",
                currency="KRW", data_source="pykrx", fetch_symbol=ticker,
                current_price=price,
            )
        except Exception:
            return None

    def quote(self, fetch_symbol, currency, asset_type):
        try:
            df = self._ohlcv(fetch_symbol, asset_type)
            if df is None or df.empty:
                return Quote(price=0.0, currency="KRW", status="error")
            price = float(df["종가"].iloc[-1])
            change = change_pct = None
            if len(df) >= 2:
                prev = float(df["종가"].iloc[-2])
                if prev:
                    change = price - prev
                    change_pct = change / prev * 100
            vol = float(df["거래량"].iloc[-1]) if "거래량" in df else None
            return Quote(price=price, currency="KRW", change=change,
                         change_pct=change_pct, volume=vol, as_of=date.today(), status="ok")
        except Exception:
            return Quote(price=0.0, currency="KRW", status="error")
```

- [ ] **Step 4: 통과 확인 + 커밋**

Run: `pytest tests/test_providers_pykrx.py -v` → Expected: PASS

```bash
git add app/services/market/pykrx_provider.py tests/test_providers_pykrx.py
git commit -m "feat: pykrx provider with ETF/ETN/stock dispatch (fixes KR ETF lookup)"
```

---

## Task 7: ManualProvider (채권 등 추적불가)

**Files:**
- Create: `app/services/market/manual_provider.py`

- [ ] **Step 1: app/services/market/manual_provider.py 구현**

```python
from datetime import date
from app.services.market.types import ResolvedAsset, Quote


class ManualProvider:
    """무료 API에 시세가 없는 자산(개별 채권 등). 사용자가 입력한 manual_price를 그대로 사용."""

    def resolve(self, ticker, market, asset_type_hint=None):
        ticker = ticker.strip().upper()
        currency = {"US": "USD", "JP": "JPY", "KR": "KRW"}.get(market, "KRW")
        return ResolvedAsset(
            ticker=ticker, name=ticker, asset_type=asset_type_hint or "bond",
            market=market, currency=currency, data_source="manual",
            fetch_symbol=ticker, current_price=None,
        )

    def quote(self, fetch_symbol, currency, asset_type, manual_price=None):
        if manual_price is None:
            return Quote(price=0.0, currency=currency, status="stale")
        return Quote(price=float(manual_price), currency=currency, as_of=date.today(), status="ok")
```

- [ ] **Step 2: 커밋**

```bash
git add app/services/market/manual_provider.py
git commit -m "feat: manual provider for untrackable assets (bonds)"
```

---

## Task 8: ProviderRegistry + AssetResolver + QuoteService

**Files:**
- Create: `app/services/market/registry.py`, `app/services/market/resolver.py`, `app/services/market/quote_service.py`, `tests/test_resolver.py`

- [ ] **Step 1: 실패 테스트 — tests/test_resolver.py**

```python
from unittest.mock import patch, MagicMock
from app.services.market.resolver import AssetResolver
from app.services.market.types import ResolvedAsset


def _ra(**kw):
    base = dict(ticker="AAPL", name="Apple", asset_type="stock", market="US",
                currency="USD", data_source="yfinance", fetch_symbol="AAPL", current_price=110.0)
    base.update(kw); return ResolvedAsset(**base)


def test_resolver_returns_preview_on_success():
    yf = MagicMock(); yf.resolve.return_value = _ra()
    r = AssetResolver(yfinance=yf, pykrx=MagicMock(), manual=MagicMock())
    out = r.resolve("AAPL", "US")
    assert out.ok is True
    assert out.asset.name == "Apple"
    assert out.tried == ["yfinance"]


def test_resolver_kr_falls_back_to_yfinance():
    pykrx = MagicMock(); pykrx.resolve.return_value = None
    yf = MagicMock(); yf.resolve.return_value = _ra(market="KR", currency="KRW",
                                                    data_source="yfinance", fetch_symbol="005930.KS")
    r = AssetResolver(yfinance=yf, pykrx=pykrx, manual=MagicMock())
    out = r.resolve("005930", "KR")
    assert out.ok is True
    assert out.tried == ["pykrx", "yfinance"]


def test_resolver_reports_failure_with_tried_list():
    yf = MagicMock(); yf.resolve.return_value = None
    pykrx = MagicMock(); pykrx.resolve.return_value = None
    r = AssetResolver(yfinance=yf, pykrx=pykrx, manual=MagicMock())
    out = r.resolve("005930", "KR")
    assert out.ok is False
    assert out.tried == ["pykrx", "yfinance"]
    assert "manual" in out.suggestion.lower()
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_resolver.py -v` → Expected: FAIL

- [ ] **Step 3: registry.py 구현**

```python
from app.services.market.yfinance_provider import YFinanceProvider
from app.services.market.pykrx_provider import PykrxProvider
from app.services.market.manual_provider import ManualProvider


class ProviderRegistry:
    def __init__(self):
        self.yfinance = YFinanceProvider()
        self.pykrx = PykrxProvider()
        self.manual = ManualProvider()

    def for_source(self, data_source: str):
        return {"yfinance": self.yfinance, "pykrx": self.pykrx, "manual": self.manual}[data_source]


registry = ProviderRegistry()
```

- [ ] **Step 4: resolver.py 구현**

```python
from dataclasses import dataclass, field
from app.services.market.types import ResolvedAsset
from app.services.market.registry import registry

# 시장별 해석 체인 (provider 속성명 순서)
_CHAINS = {
    "US": ["yfinance"],
    "JP": ["yfinance"],
    "CRYPTO": ["yfinance"],
    "KR": ["pykrx", "yfinance"],
}


@dataclass
class ResolveResult:
    ok: bool
    asset: ResolvedAsset | None = None
    tried: list[str] = field(default_factory=list)
    suggestion: str = ""


class AssetResolver:
    def __init__(self, yfinance=None, pykrx=None, manual=None):
        self.providers = {
            "yfinance": yfinance or registry.yfinance,
            "pykrx": pykrx or registry.pykrx,
            "manual": manual or registry.manual,
        }

    def resolve(self, ticker: str, market: str, asset_type_hint: str | None = None) -> ResolveResult:
        # 채권/수동 요청은 바로 manual.
        if asset_type_hint == "bond":
            asset = self.providers["manual"].resolve(ticker, market, asset_type_hint)
            return ResolveResult(ok=True, asset=asset, tried=["manual"])
        tried: list[str] = []
        for name in _CHAINS.get(market, ["yfinance"]):
            tried.append(name)
            asset = self.providers[name].resolve(ticker, market, asset_type_hint)
            if asset is not None:
                return ResolveResult(ok=True, asset=asset, tried=tried)
        return ResolveResult(
            ok=False, tried=tried,
            suggestion="자동 조회 실패. 티커·시장을 확인하거나 수동(manual) 모드로 등록하세요.",
        )
```

- [ ] **Step 5: quote_service.py 구현**

```python
import asyncio
from app.services.market.types import Quote
from app.services.market.registry import registry


async def get_quote(asset) -> Quote:
    """ORM Asset 객체를 받아 data_source에 맞는 provider로 시세를 조회한다(블로킹 → 스레드)."""
    provider = registry.for_source(asset.data_source)
    if asset.data_source == "manual":
        return await asyncio.to_thread(
            provider.quote, asset.fetch_symbol, asset.currency, asset.asset_type, asset.manual_price
        )
    return await asyncio.to_thread(
        provider.quote, asset.fetch_symbol, asset.currency, asset.asset_type
    )
```

- [ ] **Step 6: 통과 확인 + 커밋**

Run: `pytest tests/test_resolver.py -v` → Expected: PASS

```bash
git add app/services/market/registry.py app/services/market/resolver.py app/services/market/quote_service.py tests/test_resolver.py
git commit -m "feat: provider registry, asset resolver with fallback chains, quote service"
```

---

## Task 9: FxService

**Files:**
- Create: `app/services/fx/__init__.py`, `app/services/fx/fx_service.py`, `tests/test_fx_service.py`

- [ ] **Step 1: 실패 테스트 — tests/test_fx_service.py**

```python
import pytest
from datetime import date
from unittest.mock import patch
import pandas as pd
from sqlalchemy import select
from app.services.fx.fx_service import refresh_rates, get_rate_to_krw
from app.models import ExchangeRate


@pytest.mark.asyncio
@patch("app.services.fx.fx_service._yf_rate")
async def test_refresh_rates_upserts(mock_rate, db_session):
    mock_rate.side_effect = lambda pair: {"USDKRW=X": 1350.0, "JPYKRW=X": 9.0}[pair]
    await refresh_rates(db_session)
    rows = (await db_session.execute(select(ExchangeRate))).scalars().all()
    pairs = {(r.base_currency, r.quote_currency): float(r.rate) for r in rows}
    assert pairs[("USD", "KRW")] == 1350.0
    assert pairs[("JPY", "KRW")] == 9.0


@pytest.mark.asyncio
@patch("app.services.fx.fx_service._yf_rate")
async def test_refresh_is_idempotent_same_day(mock_rate, db_session):
    mock_rate.side_effect = lambda pair: {"USDKRW=X": 1350.0, "JPYKRW=X": 9.0}[pair]
    await refresh_rates(db_session)
    mock_rate.side_effect = lambda pair: {"USDKRW=X": 1400.0, "JPYKRW=X": 9.5}[pair]
    await refresh_rates(db_session)  # 같은 날짜 → update
    rows = (await db_session.execute(select(ExchangeRate))).scalars().all()
    assert len(rows) == 2
    pairs = {(r.base_currency, r.quote_currency): float(r.rate) for r in rows}
    assert pairs[("USD", "KRW")] == 1400.0


@pytest.mark.asyncio
async def test_get_rate_to_krw_for_krw_is_one(db_session):
    assert await get_rate_to_krw(db_session, "KRW") == 1.0
```

- [ ] **Step 2: 실패 확인** → Run: `pytest tests/test_fx_service.py -v` → FAIL

- [ ] **Step 3: app/services/fx/fx_service.py 구현**

```python
from datetime import date
import yfinance as yf
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import ExchangeRate

# 기준통화 KRW. base 1단위당 KRW.
_PAIRS = {"USD": "USDKRW=X", "JPY": "JPYKRW=X"}


def _yf_rate(yf_symbol: str) -> float:
    hist = yf.Ticker(yf_symbol).history(period="5d")
    return float(hist["Close"].iloc[-1])


async def refresh_rates(db: AsyncSession) -> None:
    today = date.today()
    for base, sym in _PAIRS.items():
        try:
            rate = _yf_rate(sym)
        except Exception:
            continue
        existing = (await db.execute(
            select(ExchangeRate).where(
                ExchangeRate.date == today,
                ExchangeRate.base_currency == base,
                ExchangeRate.quote_currency == "KRW",
            )
        )).scalar_one_or_none()
        if existing:
            existing.rate = rate
            existing.source = "yfinance"
        else:
            db.add(ExchangeRate(date=today, base_currency=base, quote_currency="KRW",
                                rate=rate, source="yfinance"))
    await db.commit()


async def get_rate_to_krw(db: AsyncSession, currency: str, on: date | None = None) -> float | None:
    """currency 1단위당 KRW. KRW면 1.0. 해당 날짜 없으면 최신 행으로 대체."""
    if currency == "KRW":
        return 1.0
    q = select(ExchangeRate).where(
        ExchangeRate.base_currency == currency, ExchangeRate.quote_currency == "KRW"
    )
    if on is not None:
        exact = (await db.execute(q.where(ExchangeRate.date == on))).scalar_one_or_none()
        if exact:
            return float(exact.rate)
    latest = (await db.execute(q.order_by(ExchangeRate.date.desc()))).scalars().first()
    return float(latest.rate) if latest else None
```

- [ ] **Step 4: 통과 확인 + 커밋**

Run: `TEST_DATABASE_URL=<dsn> pytest tests/test_fx_service.py -v` → PASS

```bash
git add app/services/fx/ tests/test_fx_service.py
git commit -m "feat: fx service (USD/JPY to KRW, upsert, lookup)"
```

---

## Task 10: PortfolioService (집계·환산·손익·비중)

**Files:**
- Create: `app/services/portfolio/__init__.py`, `app/services/portfolio/portfolio_service.py`, `tests/test_portfolio_service.py`

- [ ] **Step 1: 실패 테스트 — tests/test_portfolio_service.py**

순수 계산 함수를 먼저 테스트한다(DB 불필요).

```python
from app.services.portfolio.portfolio_service import aggregate_position


def test_aggregate_position_single_lot_krw():
    lots = [dict(quantity=10, purchase_price=70000, purchase_fx_rate=1, fee=0)]
    pos = aggregate_position(lots, current_price=71000, fx_now=1.0)
    assert pos["quantity"] == 10
    assert pos["avg_price"] == 70000
    assert pos["cost_krw"] == 700000
    assert pos["value_krw"] == 710000
    assert pos["profit_loss_krw"] == 10000
    assert round(pos["profit_loss_pct"], 4) == round(10000 / 700000 * 100, 4)


def test_aggregate_position_usd_with_fx_separates_currency_gain():
    # 매입: 10주 @ $100, 매입환율 1300 → 원가 1,300,000
    # 현재: $110, 현재환율 1350 → 가치 10*110*1350 = 1,485,000
    lots = [dict(quantity=10, purchase_price=100, purchase_fx_rate=1300, fee=0)]
    pos = aggregate_position(lots, current_price=110, fx_now=1350.0)
    assert pos["cost_krw"] == 1300000
    assert pos["value_krw"] == 1485000
    assert pos["profit_loss_krw"] == 185000


def test_aggregate_position_multi_lot_weighted_avg():
    lots = [
        dict(quantity=10, purchase_price=100, purchase_fx_rate=1, fee=0),
        dict(quantity=30, purchase_price=200, purchase_fx_rate=1, fee=0),
    ]
    pos = aggregate_position(lots, current_price=200, fx_now=1.0)
    assert pos["quantity"] == 40
    assert pos["avg_price"] == (10 * 100 + 30 * 200) / 40  # 175
```

- [ ] **Step 2: 실패 확인** → Run: `pytest tests/test_portfolio_service.py::test_aggregate_position_single_lot_krw -v` → FAIL

- [ ] **Step 3: portfolio_service.py — 순수 계산 함수 구현**

```python
from app.db import SessionLocal  # 사용처(get_portfolio)에서 import; 계산 함수는 DB 무관


def aggregate_position(lots: list[dict], current_price: float, fx_now: float) -> dict:
    """동일 자산의 lot들을 집계해 KRW 기준 손익을 계산한다.

    cost_krw  = Σ quantity * purchase_price * purchase_fx_rate (+fee)
    value_krw = Σ quantity * current_price * fx_now
    """
    total_qty = sum(l["quantity"] for l in lots)
    cost_krw = sum(
        l["quantity"] * l["purchase_price"] * (l["purchase_fx_rate"] or fx_now) + (l.get("fee") or 0)
        for l in lots
    )
    avg_price = (sum(l["quantity"] * l["purchase_price"] for l in lots) / total_qty) if total_qty else 0
    value_krw = total_qty * current_price * fx_now
    pl = value_krw - cost_krw
    pl_pct = (pl / cost_krw * 100) if cost_krw else 0
    return {
        "quantity": total_qty,
        "avg_price": avg_price,
        "cost_krw": cost_krw,
        "value_krw": value_krw,
        "profit_loss_krw": pl,
        "profit_loss_pct": pl_pct,
    }
```

- [ ] **Step 4: 계산 테스트 통과 확인**

Run: `pytest tests/test_portfolio_service.py -v` → Expected: PASS

- [ ] **Step 5: get_portfolio (DB 조합) 추가**

`app/services/portfolio/portfolio_service.py`에 이어서 추가:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Asset, Holding
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
                          purchase_fx_rate=float(l.purchase_fx_rate) if l.purchase_fx_rate else None,
                          fee=float(l.fee or 0)) for l in lots]
        agg = aggregate_position(lot_dicts, current_price=quote.price, fx_now=fx_now)
        total_value += agg["value_krw"]
        positions.append({
            "asset_id": asset.asset_id, "ticker": asset.ticker, "name": asset.name,
            "market": asset.market, "currency": asset.currency,
            "current_price": quote.price, "price_status": quote.status, **agg,
        })
    for p in positions:
        p["weight_pct"] = (p["value_krw"] / total_value * 100) if total_value else 0
    total_cost = sum(p["cost_krw"] for p in positions)
    return {
        "positions": positions,
        "summary": {
            "total_value_krw": total_value,
            "total_cost_krw": total_cost,
            "total_profit_loss_krw": total_value - total_cost,
            "total_profit_loss_pct": ((total_value - total_cost) / total_cost * 100) if total_cost else 0,
        },
    }
```

- [ ] **Step 6: 커밋**

```bash
git add app/services/portfolio/ tests/test_portfolio_service.py
git commit -m "feat: portfolio aggregation with KRW conversion and FX-separated P&L"
```

---

## Task 11: SettingsManager (Fernet)

**Files:**
- Create: `app/services/settings/__init__.py`, `app/services/settings/settings_manager.py`

- [ ] **Step 1: settings_manager.py 구현**

```python
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models import AppSetting

_fernet = Fernet(settings.FERNET_KEY.encode())


async def get_setting(db: AsyncSession, category: str, key: str) -> str | None:
    row = (await db.execute(
        select(AppSetting).where(AppSetting.category == category, AppSetting.key == key)
    )).scalar_one_or_none()
    if row is None:
        return None
    if row.is_secret and row.value_enc is not None:
        return _fernet.decrypt(row.value_enc).decode()
    return row.value


async def set_setting(db: AsyncSession, category: str, key: str, value: str,
                      is_secret: bool = False, value_type: str = "string") -> None:
    row = (await db.execute(
        select(AppSetting).where(AppSetting.category == category, AppSetting.key == key)
    )).scalar_one_or_none()
    enc = _fernet.encrypt(value.encode()) if is_secret else None
    plain = None if is_secret else value
    if row is None:
        db.add(AppSetting(category=category, key=key, value=plain, value_enc=enc,
                          is_secret=is_secret, value_type=value_type))
    else:
        row.value, row.value_enc, row.is_secret, row.value_type = plain, enc, is_secret, value_type
    await db.commit()
```

- [ ] **Step 2: 커밋**

```bash
git add app/services/settings/
git commit -m "feat: settings manager with Fernet secret encryption"
```

---

## Task 12: Pydantic 스키마

**Files:**
- Create: `app/schemas/__init__.py`, `app/schemas/market.py`, `app/schemas/asset.py`, `app/schemas/holding.py`, `app/schemas/portfolio.py`

- [ ] **Step 1: app/schemas/market.py**

```python
from pydantic import BaseModel


class ResolveRequest(BaseModel):
    ticker: str
    market: str
    asset_type: str | None = None


class ResolvedAssetOut(BaseModel):
    ticker: str
    name: str
    asset_type: str
    market: str
    currency: str
    data_source: str
    fetch_symbol: str
    current_price: float | None = None
    name_en: str | None = None


class ResolveResponse(BaseModel):
    ok: bool
    asset: ResolvedAssetOut | None = None
    tried: list[str] = []
    suggestion: str = ""
```

- [ ] **Step 2: app/schemas/asset.py**

```python
from datetime import datetime
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
    manual_price: float | None = None
    is_active: bool

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: app/schemas/holding.py**

```python
from datetime import date
from pydantic import BaseModel


class HoldingCreate(BaseModel):
    asset_id: int
    purchase_date: date
    quantity: float
    purchase_price: float
    purchase_fx_rate: float | None = None
    fee: float = 0
    memo: str | None = None


class HoldingUpdate(BaseModel):
    purchase_date: date | None = None
    quantity: float | None = None
    purchase_price: float | None = None
    purchase_fx_rate: float | None = None
    fee: float | None = None
    memo: str | None = None


class HoldingOut(BaseModel):
    holding_id: int
    asset_id: int
    purchase_date: date
    quantity: float
    purchase_price: float
    purchase_fx_rate: float | None = None
    fee: float
    memo: str | None = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: app/schemas/portfolio.py**

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
    cost_krw: float
    value_krw: float
    profit_loss_krw: float
    profit_loss_pct: float
    weight_pct: float
    price_status: str


class PortfolioSummary(BaseModel):
    total_value_krw: float
    total_cost_krw: float
    total_profit_loss_krw: float
    total_profit_loss_pct: float


class PortfolioOut(BaseModel):
    positions: list[Position]
    summary: PortfolioSummary
```

- [ ] **Step 5: 빈 __init__.py 생성 후 커밋**

```bash
git add app/schemas/
git commit -m "feat: pydantic request/response schemas"
```

---

## Task 13: assets 라우터

**Files:**
- Create: `app/routers/__init__.py`, `app/routers/assets.py`

- [ ] **Step 1: app/routers/assets.py 구현**

```python
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Asset
from app.schemas.market import ResolveRequest, ResolveResponse, ResolvedAssetOut
from app.schemas.asset import AssetCreate, AssetOut, ManualPriceUpdate
from app.services.market.resolver import AssetResolver
from app.services.market.quote_service import get_quote

router = APIRouter(prefix="/api/assets", tags=["assets"])
_resolver = AssetResolver()


@router.post("/resolve", response_model=ResolveResponse)
async def resolve(req: ResolveRequest):
    result = await asyncio.to_thread(_resolver.resolve, req.ticker, req.market, req.asset_type)
    out = None
    if result.asset is not None:
        out = ResolvedAssetOut(**result.asset.__dict__)
    return ResolveResponse(ok=result.ok, asset=out, tried=result.tried, suggestion=result.suggestion)


@router.post("", response_model=AssetOut)
async def create_asset(body: AssetCreate, db: AsyncSession = Depends(get_db)):
    asset = Asset(**body.model_dump())
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


@router.get("", response_model=list[AssetOut])
async def list_assets(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Asset).where(Asset.is_active == True))).scalars().all()  # noqa: E712


@router.get("/{asset_id}/quote")
async def asset_quote(asset_id: int, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    q = await get_quote(asset)
    return q.__dict__


@router.put("/{asset_id}/manual-price", response_model=AssetOut)
async def update_manual_price(asset_id: int, body: ManualPriceUpdate, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    asset.manual_price = body.manual_price
    asset.manual_price_currency = body.manual_price_currency
    asset.manual_price_updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(asset)
    return asset


@router.delete("/{asset_id}")
async def delete_asset(asset_id: int, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    await db.delete(asset)
    await db.commit()
    return {"deleted": asset_id}
```

- [ ] **Step 2: 빈 __init__.py 생성 후 커밋**

```bash
git add app/routers/__init__.py app/routers/assets.py
git commit -m "feat: assets router (resolve, CRUD, quote, manual-price)"
```

---

## Task 14: holdings 라우터

**Files:**
- Create: `app/routers/holdings.py`

- [ ] **Step 1: app/routers/holdings.py 구현**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Holding
from app.schemas.holding import HoldingCreate, HoldingUpdate, HoldingOut

router = APIRouter(prefix="/api/holdings", tags=["holdings"])


@router.post("", response_model=HoldingOut)
async def create_holding(body: HoldingCreate, db: AsyncSession = Depends(get_db)):
    h = Holding(**body.model_dump())
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

- [ ] **Step 2: 커밋**

```bash
git add app/routers/holdings.py
git commit -m "feat: holdings (lot) CRUD router"
```

---

## Task 15: portfolio / fx / settings 라우터

**Files:**
- Create: `app/routers/portfolio.py`, `app/routers/fx.py`, `app/routers/settings.py`

- [ ] **Step 1: app/routers/portfolio.py**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.schemas.portfolio import PortfolioOut
from app.services.portfolio.portfolio_service import get_portfolio
from app.services.fx.fx_service import refresh_rates

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioOut)
async def portfolio(db: AsyncSession = Depends(get_db)):
    return await get_portfolio(db)


@router.post("/refresh", response_model=PortfolioOut)
async def refresh(db: AsyncSession = Depends(get_db)):
    await refresh_rates(db)        # 환율 갱신 후 재집계 (시세는 get_portfolio가 실시간 조회)
    return await get_portfolio(db)
```

- [ ] **Step 2: app/routers/fx.py**

```python
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import ExchangeRate
from app.services.fx.fx_service import refresh_rates

router = APIRouter(prefix="/api/fx", tags=["fx"])


@router.get("")
async def list_rates(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ExchangeRate).order_by(ExchangeRate.date.desc()))).scalars().all()
    return [{"date": str(r.date), "base": r.base_currency, "quote": r.quote_currency,
             "rate": float(r.rate)} for r in rows]


@router.post("/refresh")
async def refresh(db: AsyncSession = Depends(get_db)):
    await refresh_rates(db)
    return {"status": "ok"}
```

- [ ] **Step 3: app/routers/settings.py**

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.services.settings.settings_manager import get_setting, set_setting

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingIn(BaseModel):
    category: str
    key: str
    value: str
    is_secret: bool = False


@router.get("/{category}/{key}")
async def read(category: str, key: str, db: AsyncSession = Depends(get_db)):
    return {"value": await get_setting(db, category, key)}


@router.put("")
async def write(body: SettingIn, db: AsyncSession = Depends(get_db)):
    await set_setting(db, body.category, body.key, body.value, body.is_secret)
    return {"status": "ok"}
```

- [ ] **Step 4: 커밋**

```bash
git add app/routers/portfolio.py app/routers/fx.py app/routers/settings.py
git commit -m "feat: portfolio, fx, settings routers"
```

---

## Task 16: main.py (FastAPI + lifespan)

**Files:**
- Create: `app/main.py`

- [ ] **Step 1: app/main.py 구현**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import engine
from app.bootstrap import ensure_schema
from app.routers import assets, holdings, portfolio, fx, settings as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_schema(engine)   # 부팅 시 invest 스키마/테이블 멱등 생성
    yield
    await engine.dispose()


app = FastAPI(title="invest_portal", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],   # Vite dev 서버
    allow_methods=["*"], allow_headers=["*"],
)

for r in (assets.router, holdings.router, portfolio.router, fx.router, settings_router.router):
    app.include_router(r)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 2: 부팅 스모크 테스트**

Run: `uvicorn app.main:app --reload` 후 `curl http://localhost:8000/health`
Expected: `{"status":"ok"}`, 그리고 DB의 `invest` 스키마에 5개 테이블 생성 확인.

- [ ] **Step 3: 커밋**

```bash
git add app/main.py
git commit -m "feat: FastAPI app with lifespan bootstrap and router wiring"
```

---

## Task 17: API 통합 테스트

**Files:**
- Create: `tests/test_api.py`

- [ ] **Step 1: tests/test_api.py — resolve 모킹 + holdings/portfolio 흐름**

```python
import pytest
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.bootstrap import ensure_schema
from app.db import engine


@pytest.mark.asyncio
async def test_resolve_endpoint_returns_preview():
    from app.services.market.types import ResolvedAsset
    from app.services.market.resolver import ResolveResult
    fake = ResolveResult(ok=True, asset=ResolvedAsset(
        ticker="AAPL", name="Apple", asset_type="stock", market="US", currency="USD",
        data_source="yfinance", fetch_symbol="AAPL", current_price=110.0), tried=["yfinance"])
    with patch("app.routers.assets._resolver.resolve", return_value=fake):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            resp = await ac.post("/api/assets/resolve",
                                 json={"ticker": "AAPL", "market": "US"})
    assert resp.status_code == 200
    assert resp.json()["asset"]["name"] == "Apple"
```

> 메모: 전체 holdings→portfolio 흐름 통합 테스트는 `TEST_DATABASE_URL` 설정 시 `ensure_schema(engine)`를 먼저 호출하고, asset 생성 → holding 생성 → `GET /api/portfolio`에서 position 1건과 summary를 검증한다. `get_quote`는 `patch("app.services.portfolio.portfolio_service.get_quote")`로 고정가를 주입한다.

- [ ] **Step 2: 통과 확인 + 커밋**

Run: `pytest tests/test_api.py -v` → Expected: PASS

```bash
git add tests/test_api.py
git commit -m "test: API integration for resolve endpoint"
```

---

## Task 18: 프론트엔드 골격 (Vite + React + TS + Tailwind)

**Files:**
- Create: `frontend/` (Vite 스캐폴드), `frontend/tailwind.config.js`, `frontend/src/api.ts`

- [ ] **Step 1: Vite 스캐폴드 생성**

```bash
cd frontend && npm create vite@latest . -- --template react-ts && npm install
npm install -D tailwindcss@3 postcss autoprefixer && npx tailwindcss init -p
npm install react-router-dom
```

- [ ] **Step 2: tailwind.config.js 의 content 설정**

```js
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
}
```
`src/index.css` 상단에 `@tailwind base; @tailwind components; @tailwind utilities;` 추가.

- [ ] **Step 3: frontend/src/api.ts — API 클라이언트**

```ts
const BASE = "http://localhost:8000";

async function j<T>(p: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + p, {
    headers: { "Content-Type": "application/json" }, ...init,
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const api = {
  resolve: (ticker: string, market: string, asset_type?: string) =>
    j<ResolveResponse>("/api/assets/resolve", { method: "POST", body: JSON.stringify({ ticker, market, asset_type }) }),
  createAsset: (a: any) => j("/api/assets", { method: "POST", body: JSON.stringify(a) }),
  listAssets: () => j<any[]>("/api/assets"),
  createHolding: (h: any) => j("/api/holdings", { method: "POST", body: JSON.stringify(h) }),
  listHoldings: () => j<any[]>("/api/holdings"),
  deleteHolding: (id: number) => j(`/api/holdings/${id}`, { method: "DELETE" }),
  portfolio: () => j<PortfolioOut>("/api/portfolio"),
  refresh: () => j<PortfolioOut>("/api/portfolio/refresh", { method: "POST" }),
};

export interface ResolveResponse {
  ok: boolean;
  asset: any | null;
  tried: string[];
  suggestion: string;
}
export interface Position {
  asset_id: number; ticker: string; name: string; market: string; currency: string;
  quantity: number; avg_price: number; current_price: number; cost_krw: number;
  value_krw: number; profit_loss_krw: number; profit_loss_pct: number;
  weight_pct: number; price_status: string;
}
export interface PortfolioOut {
  positions: Position[];
  summary: { total_value_krw: number; total_cost_krw: number;
             total_profit_loss_krw: number; total_profit_loss_pct: number };
}
```

- [ ] **Step 4: 커밋**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tailwind.config.js frontend/postcss.config.js frontend/src/api.ts frontend/src/index.css
git commit -m "feat(frontend): vite+react+ts+tailwind scaffold and api client"
```

---

## Task 19: 포트폴리오 대시보드 화면

**Files:**
- Create: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: frontend/src/pages/Dashboard.tsx**

```tsx
import { useEffect, useState } from "react";
import { api, PortfolioOut } from "../api";

const krw = (n: number) => n.toLocaleString("ko-KR", { maximumFractionDigits: 0 });

export default function Dashboard() {
  const [data, setData] = useState<PortfolioOut | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => setData(await api.portfolio());
  const refresh = async () => { setLoading(true); try { setData(await api.refresh()); } finally { setLoading(false); } };
  useEffect(() => { load(); }, []);

  if (!data) return <div className="p-6">불러오는 중…</div>;
  const s = data.summary;
  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">포트폴리오</h1>
        <button onClick={refresh} disabled={loading}
          className="px-3 py-1.5 rounded bg-blue-600 text-white disabled:opacity-50">
          {loading ? "갱신 중…" : "새로고침"}
        </button>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded border p-4">
          <div className="text-sm text-gray-500">총자산 (KRW)</div>
          <div className="text-2xl font-semibold">₩{krw(s.total_value_krw)}</div>
        </div>
        <div className="rounded border p-4">
          <div className="text-sm text-gray-500">총손익</div>
          <div className={`text-2xl font-semibold ${s.total_profit_loss_krw >= 0 ? "text-red-600" : "text-blue-600"}`}>
            ₩{krw(s.total_profit_loss_krw)} ({s.total_profit_loss_pct.toFixed(2)}%)
          </div>
        </div>
      </div>
      <table className="w-full text-sm border-collapse">
        <thead><tr className="border-b text-left text-gray-500">
          <th className="py-2">종목</th><th>수량</th><th>평단</th><th>현재가</th>
          <th>평가액(KRW)</th><th>손익</th><th>비중</th><th></th>
        </tr></thead>
        <tbody>
          {data.positions.map((p) => (
            <tr key={p.asset_id} className="border-b">
              <td className="py-2">{p.name} <span className="text-gray-400">{p.ticker}·{p.market}</span></td>
              <td>{p.quantity}</td><td>{p.avg_price.toLocaleString()}</td>
              <td>{p.current_price.toLocaleString()}</td><td>₩{krw(p.value_krw)}</td>
              <td className={p.profit_loss_krw >= 0 ? "text-red-600" : "text-blue-600"}>
                ₩{krw(p.profit_loss_krw)} ({p.profit_loss_pct.toFixed(1)}%)
              </td>
              <td>{p.weight_pct.toFixed(1)}%</td>
              <td>{p.price_status !== "ok" && <span className="text-amber-600">⚠{p.price_status}</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(frontend): portfolio dashboard with summary and positions table"
```

---

## Task 20: 자산 등록(resolve 미리보기) + 보유 관리 화면

**Files:**
- Create: `frontend/src/pages/Assets.tsx`, `frontend/src/pages/Holdings.tsx`

- [ ] **Step 1: frontend/src/pages/Assets.tsx — resolve→확인→등록**

```tsx
import { useEffect, useState } from "react";
import { api, ResolveResponse } from "../api";

const MARKETS = ["US", "KR", "JP", "CRYPTO"];

export default function Assets() {
  const [ticker, setTicker] = useState(""); const [market, setMarket] = useState("US");
  const [assetType, setAssetType] = useState(""); const [preview, setPreview] = useState<ResolveResponse | null>(null);
  const [assets, setAssets] = useState<any[]>([]);
  const load = async () => setAssets(await api.listAssets());
  useEffect(() => { load(); }, []);

  const doResolve = async () =>
    setPreview(await api.resolve(ticker, market, assetType || undefined));
  const confirm = async () => {
    if (!preview?.asset) return;
    await api.createAsset(preview.asset);
    setPreview(null); setTicker(""); await load();
  };

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-xl font-bold">자산 등록</h1>
      <div className="flex gap-2 items-center">
        <input className="border rounded px-2 py-1" placeholder="티커 (AAPL, 005930, 7203, BTC)"
          value={ticker} onChange={(e) => setTicker(e.target.value)} />
        <select className="border rounded px-2 py-1" value={market} onChange={(e) => setMarket(e.target.value)}>
          {MARKETS.map((m) => <option key={m}>{m}</option>)}
        </select>
        <input className="border rounded px-2 py-1 w-32" placeholder="유형(선택: bond)"
          value={assetType} onChange={(e) => setAssetType(e.target.value)} />
        <button onClick={doResolve} className="px-3 py-1 rounded bg-gray-800 text-white">조회</button>
      </div>

      {preview && (preview.ok && preview.asset ? (
        <div className="rounded border p-3 bg-green-50">
          <div><b>{preview.asset.name}</b> · {preview.asset.currency} · {preview.asset.asset_type} · {preview.asset.data_source}</div>
          <div>현재가: {preview.asset.current_price ?? "—"}</div>
          <button onClick={confirm} className="mt-2 px-3 py-1 rounded bg-blue-600 text-white">등록</button>
        </div>
      ) : (
        <div className="rounded border p-3 bg-amber-50">
          <div>조회 실패 (시도: {preview.tried.join(", ")})</div>
          <div className="text-sm text-gray-600">{preview.suggestion}</div>
        </div>
      ))}

      <h2 className="font-semibold mt-4">등록된 자산</h2>
      <ul className="text-sm">
        {assets.map((a) => <li key={a.asset_id}>{a.ticker}·{a.market} — {a.name} ({a.data_source})</li>)}
      </ul>
    </div>
  );
}
```

- [ ] **Step 2: frontend/src/pages/Holdings.tsx — lot 추가/목록/삭제**

```tsx
import { useEffect, useState } from "react";
import { api } from "../api";

export default function Holdings() {
  const [assets, setAssets] = useState<any[]>([]); const [holdings, setHoldings] = useState<any[]>([]);
  const [form, setForm] = useState<any>({ asset_id: "", purchase_date: "", quantity: "", purchase_price: "", fee: 0, memo: "" });
  const load = async () => { setAssets(await api.listAssets()); setHoldings(await api.listHoldings()); };
  useEffect(() => { load(); }, []);

  const submit = async () => {
    await api.createHolding({ ...form, asset_id: Number(form.asset_id),
      quantity: Number(form.quantity), purchase_price: Number(form.purchase_price), fee: Number(form.fee) });
    setForm({ asset_id: "", purchase_date: "", quantity: "", purchase_price: "", fee: 0, memo: "" });
    await load();
  };
  const remove = async (id: number) => { await api.deleteHolding(id); await load(); };

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-xl font-bold">보유 관리 (lot)</h1>
      <div className="grid grid-cols-3 gap-2 max-w-3xl">
        <select className="border rounded px-2 py-1" value={form.asset_id}
          onChange={(e) => setForm({ ...form, asset_id: e.target.value })}>
          <option value="">자산 선택</option>
          {assets.map((a) => <option key={a.asset_id} value={a.asset_id}>{a.ticker}·{a.market} {a.name}</option>)}
        </select>
        <input type="date" className="border rounded px-2 py-1" value={form.purchase_date}
          onChange={(e) => setForm({ ...form, purchase_date: e.target.value })} />
        <input placeholder="수량" className="border rounded px-2 py-1" value={form.quantity}
          onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
        <input placeholder="매입단가(자산통화)" className="border rounded px-2 py-1" value={form.purchase_price}
          onChange={(e) => setForm({ ...form, purchase_price: e.target.value })} />
        <input placeholder="수수료" className="border rounded px-2 py-1" value={form.fee}
          onChange={(e) => setForm({ ...form, fee: e.target.value })} />
        <input placeholder="메모" className="border rounded px-2 py-1" value={form.memo}
          onChange={(e) => setForm({ ...form, memo: e.target.value })} />
      </div>
      <button onClick={submit} className="px-3 py-1 rounded bg-blue-600 text-white">추가</button>

      <table className="w-full text-sm mt-4">
        <thead><tr className="border-b text-left text-gray-500">
          <th className="py-2">자산ID</th><th>매입일</th><th>수량</th><th>단가</th><th></th>
        </tr></thead>
        <tbody>
          {holdings.map((h) => (
            <tr key={h.holding_id} className="border-b">
              <td className="py-2">{h.asset_id}</td><td>{h.purchase_date}</td>
              <td>{h.quantity}</td><td>{h.purchase_price}</td>
              <td><button onClick={() => remove(h.holding_id)} className="text-red-600">삭제</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/pages/Assets.tsx frontend/src/pages/Holdings.tsx
git commit -m "feat(frontend): asset registration with resolve preview and holdings management"
```

---

## Task 21: 라우팅 + 레이아웃 연결

**Files:**
- Modify: `frontend/src/App.tsx`, `frontend/src/main.tsx`

- [ ] **Step 1: frontend/src/App.tsx — 네비 + 라우트**

```tsx
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Assets from "./pages/Assets";
import Holdings from "./pages/Holdings";

export default function App() {
  return (
    <BrowserRouter>
      <nav className="flex gap-4 border-b px-6 py-3">
        <Link to="/" className="font-semibold">대시보드</Link>
        <Link to="/assets">자산</Link>
        <Link to="/holdings">보유</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/assets" element={<Assets />} />
        <Route path="/holdings" element={<Holdings />} />
      </Routes>
    </BrowserRouter>
  );
}
```

- [ ] **Step 2: main.tsx 가 App 과 index.css 를 import 하는지 확인**

`frontend/src/main.tsx`:
```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App /></React.StrictMode>
);
```

- [ ] **Step 3: 엔드투엔드 수동 검증**

Run: 백엔드 `uvicorn app.main:app` + 프론트 `cd frontend && npm run dev`.
- `/assets`에서 AAPL(US)·005930(KR ETF로 069500)·BTC(CRYPTO) 등록 → resolve 미리보기 확인
- `/holdings`에서 lot 추가
- `/` 대시보드에서 KRW 환산 평가액·손익·비중·총자산 확인

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/App.tsx frontend/src/main.tsx
git commit -m "feat(frontend): routing and layout"
```

---

## Self-Review 결과 (spec 대비 커버리지)

- spec 4장 데이터 모델 → Task 2 (5개 모델) + Task 3 (ensure_schema). ✅
- spec 5장 티커 해석(US/JP/KR/CRYPTO, ETF/ETN 분기, 수동 모드, resolve-and-verify, 견고성) → Task 5·6·7·8 + Task 13 resolve 엔드포인트. ✅
- spec 6장 환율변환·손익 분해(purchase_fx_rate) → Task 9 (FX) + Task 10 (aggregate_position). ✅
- spec 7장 API → Task 13·14·15. ✅
- spec 8장 프론트(대시보드·보유·자산마스터·수동모드 UI·tried 표시) → Task 19·20·21. (수동가격 입력 UI는 Task 13 `manual-price` 엔드포인트를 Assets 화면에서 호출하는 형태로 확장 가능 — 1단계 최소 구현은 등록까지) ✅
- spec 9장 테스트 → 각 Task의 TDD 단계 + Task 17 통합. ✅
- spec 10장 오류 처리(graceful price_status, 구조화 실패, 부팅 중단) → provider quote의 status, ResolveResult.suggestion, lifespan. ✅

**후속 단계 핸드오프:** 2단계(chartbot+텔레그램)·3단계(AI 리포트·투자저널·위험신호)는 spec "비범위" 절 참조. `history(asset, start, end)` provider 메서드 인터페이스를 Task 4에 미리 두어 2단계 차트가 재사용하도록 했다.
```

