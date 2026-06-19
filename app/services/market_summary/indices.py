"""주요 지수 현재가·전일대비%. 지수는 DB 자산이 아니라 yfinance 직접 조회."""
import asyncio

import yfinance as yf

from app.services.market._num import finite

INDICES = {
    "US": [("^GSPC", "S&P 500"), ("^IXIC", "NASDAQ"), ("^DJI", "다우")],
    "KR": [("^KS11", "KOSPI"), ("^KQ11", "KOSDAQ")],
}


def _fetch(symbol: str):
    """(price, change_pct) 또는 None(실패)."""
    try:
        hist = yf.Ticker(symbol).history(period="5d")
    except Exception:
        return None
    if hist is None or hist.empty:
        return None
    close = hist["Close"]
    price = finite(close.iloc[-1])
    if price is None:
        return None
    chg = None
    if len(close) >= 2:
        prev = finite(close.iloc[-2])
        if prev:
            chg = (price - prev) / prev * 100
    return price, chg


async def index_lines(market: str) -> list[dict]:
    out: list[dict] = []
    for symbol, name in INDICES.get(market, []):
        r = await asyncio.to_thread(_fetch, symbol)
        if r is None:
            continue
        price, chg = r
        out.append({"name": name, "price": price, "change_pct": chg})
    return out
