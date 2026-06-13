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
