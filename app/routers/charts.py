import asyncio
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Asset
from app.services.market.history_service import get_history
from app.services.chart.chart_service import generate_ta_chart, to_weekly

router = APIRouter(prefix="/api/charts", tags=["charts"])

# period별 일봉 조회 일수
_DAYS = {"daily": 730, "weekly": 1825}


async def _build_png(db: AsyncSession, asset_id: int, period: str) -> bytes:
    if period not in _DAYS:
        raise HTTPException(422, "period는 daily 또는 weekly")
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    df = await get_history(asset, _DAYS[period])
    if df is None or len(df) < 20:
        raise HTTPException(422, "차트용 시세 이력을 가져올 수 없습니다(수동/이력없음 자산이거나 데이터 부족).")
    if period == "weekly":
        df = to_weekly(df)
        if len(df) < 20:
            raise HTTPException(422, "주봉 데이터가 부족합니다.")
    label = "WEEKLY" if period == "weekly" else "DAILY"
    return await asyncio.to_thread(generate_ta_chart, df, asset.ticker, asset.name, label)


@router.get("/{asset_id}")
async def chart(asset_id: int, period: str = Query("daily"), db: AsyncSession = Depends(get_db)):
    png = await _build_png(db, asset_id, period)
    return StreamingResponse(io.BytesIO(png), media_type="image/png")
