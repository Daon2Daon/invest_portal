import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Asset
from app.services.chart.chart_builder import build_png, ChartDataError
from app.services.notification import telegram_service, chart_dispatch
from app.services.ai import chart_analyzer
from app.services.ai.llm_client import LiteLLMError

router = APIRouter(prefix="/api/charts", tags=["charts"])


async def _build_png(db: AsyncSession, asset_id: int, period: str) -> bytes:
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    try:
        return await build_png(asset, period)
    except ChartDataError as e:
        raise HTTPException(422, str(e))


@router.get("/{asset_id}")
async def chart(asset_id: int, period: str = Query("daily"), db: AsyncSession = Depends(get_db)):
    png = await _build_png(db, asset_id, period)
    # 시세는 수시로 바뀌므로 브라우저가 옛 PNG를 재사용하지 않도록 캐시 금지.
    return StreamingResponse(io.BytesIO(png), media_type="image/png",
                             headers={"Cache-Control": "no-store"})


@router.post("/{asset_id}/analyze")
async def analyze(asset_id: int, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    images = [(await _build_png(db, asset_id, p), "image/png") for p in ("daily", "weekly")]
    try:
        text = await chart_analyzer.analyze_raw(db, images, asset.ticker, asset.name, asset.market)
    except (chart_analyzer.AnalysisDisabled, chart_analyzer.AnalysisNotConfigured) as e:
        raise HTTPException(409, str(e))
    except LiteLLMError as e:
        raise HTTPException(502, str(e))
    return {"analysis": text}


@router.post("/{asset_id}/send-telegram")
async def send_telegram(asset_id: int, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    try:
        return await chart_dispatch.send_chart_telegram(db, asset)
    except telegram_service.TelegramNotConfigured as e:
        raise HTTPException(409, str(e))
    except ChartDataError as e:
        raise HTTPException(422, str(e))
