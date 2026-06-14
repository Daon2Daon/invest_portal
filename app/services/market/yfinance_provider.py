from datetime import date, timedelta
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

_MARKET_CURRENCY = {"US": "USD", "JP": "JPY", "CRYPTO": "USD", "KR": "KRW"}


def _candidate_symbols(ticker: str, market: str) -> list[str]:
    """시장별 yfinance 심볼 후보. KR은 .KS(코스피)→.KQ(코스닥) 순으로 시도한다.
    KR은 pykrx 폴백 경로로, 특히 pykrx가 ETF를 못 잡을 때 yfinance가 받는다."""
    t = ticker.strip().upper()
    if market == "JP":
        return [t if t.endswith(".T") else f"{t}.T"]
    if market == "CRYPTO":
        return [t if "-" in t else f"{t}-USD"]
    if market == "KR":
        if t.endswith((".KS", ".KQ")):
            return [t]
        return [f"{t}.KS", f"{t}.KQ"]
    return [t]  # US (지수는 사용자가 ^ 포함해 입력)


class YFinanceProvider:
    def resolve(self, ticker, market, asset_type_hint=None):
        for symbol in _candidate_symbols(ticker, market):
            try:
                inst = yf.Ticker(symbol)
                hist = inst.history(period="7d")
                if hist is None or hist.empty:
                    continue
                price = finite(hist["Close"].iloc[-1])
                if price is None:
                    continue
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
                continue
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

    def history(self, fetch_symbol, market, days):
        try:
            start = (date.today() - timedelta(days=days)).isoformat()
            df = yf.Ticker(fetch_symbol).history(start=start, auto_adjust=False)
            if df is None or df.empty:
                return None
            if not all(c in df.columns for c in ["Open", "High", "Low", "Close", "Volume"]):
                return None
            return df[["Open", "High", "Low", "Close", "Volume"]].copy()
        except Exception:
            return None
