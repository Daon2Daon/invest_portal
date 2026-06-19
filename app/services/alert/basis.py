"""알림 기준가 조회. WEEK52는 yfinance 호출 절감을 위해 자산별 TTL 캐시(기본 1시간)."""
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Holding
from app.services.market.history_service import get_history

_WEEK52_TTL = 3600.0
_WEEK52_CACHE: dict[int, tuple[float, float, float]] = {}   # asset_id -> (high, low, fetched_monotonic)


def clear_week52_cache() -> None:
    _WEEK52_CACHE.clear()


async def _purchase_avg(db: AsyncSession, asset_id: int) -> float | None:
    lots = (await db.execute(
        select(Holding).where(Holding.asset_id == asset_id)
    )).scalars().all()
    total_qty = sum(float(l.quantity) for l in lots)
    if not lots or total_qty == 0:
        return None
    return sum(float(l.quantity) * float(l.purchase_price) for l in lots) / total_qty


async def _week52(db: AsyncSession, asset) -> tuple[float, float] | None:
    cached = _WEEK52_CACHE.get(asset.asset_id)
    if cached and (time.monotonic() - cached[2]) < _WEEK52_TTL:
        return cached[0], cached[1]
    df = await get_history(asset, 365)
    if df is None or df.empty:
        return None
    high = float(df["High"].max())
    low = float(df["Low"].min())
    _WEEK52_CACHE[asset.asset_id] = (high, low, time.monotonic())
    return high, low


async def resolve_basis_price(db: AsyncSession, asset, basis: str) -> float | None:
    """ABSOLUTE→None(목표가가 value), PURCHASE_AVG→가중평균, WEEK52_*→고/저점. 불가 시 None."""
    if basis == "ABSOLUTE":
        return None
    if basis == "PURCHASE_AVG":
        return await _purchase_avg(db, asset.asset_id)
    if basis in ("WEEK52_HIGH", "WEEK52_LOW"):
        hl = await _week52(db, asset)
        if hl is None:
            return None
        return hl[0] if basis == "WEEK52_HIGH" else hl[1]
    return None
