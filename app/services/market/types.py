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
