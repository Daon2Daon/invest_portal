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
