from datetime import date
import yfinance as yf
from app.services.market.types import ResolvedAsset, Quote
from app.services.market._num import finite

# yfinance quoteType → 내부 asset_type
_QUOTE_TYPE_MAP = {
    "EQUITY": "stock",
    "ETF": "etf",
    "INDEX": "index",
    "MUTUALFUND": "fund",
    "CRYPTOCURRENCY": "crypto",
    "FUTURE": "commodity",
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
            price = finite(hist["Close"].iloc[-1])
            if price is None:
                return None
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
            price = finite(close.iloc[-1])
            if price is None:
                return Quote(price=0.0, currency=currency, status="error")
            change = change_pct = None
            if len(close) >= 2:
                prev = finite(close.iloc[-2])
                if prev:
                    change = finite(price - prev)
                    change_pct = finite(change / prev * 100) if change is not None else None
            vol = finite(hist["Volume"].iloc[-1]) if "Volume" in hist else None
            return Quote(price=price, currency=currency, change=change,
                         change_pct=change_pct, volume=vol, as_of=date.today(), status="ok")
        except Exception:
            return Quote(price=0.0, currency=currency, status="error")
