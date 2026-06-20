from datetime import date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.services.snapshot import snapshot_store

router = APIRouter(prefix="/api/trend", tags=["trend"])

_DAYS = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}


def period_to_since(period: str, today: date) -> date | None:
    """기간 문자열 → 시작일. ALL=None, 미지/누락=1M(30일) 폴백."""
    if period == "ALL":
        return None
    return today - timedelta(days=_DAYS.get(period, 30))


@router.get("")
async def trend(period: str = "1M", db: AsyncSession = Depends(get_db)):
    since = period_to_since(period, date.today())
    rows = await snapshot_store.list_snapshots(db, since)
    return [
        {
            "date": r.date.isoformat(),
            "total_value_krw": float(r.total_value_krw),
            "total_cost_krw": float(r.total_cost_krw),
            "total_pl_krw": float(r.total_pl_krw),
            "total_cash_krw": float(r.total_cash_krw),
            "allocation": r.allocation,
        }
        for r in rows
    ]
