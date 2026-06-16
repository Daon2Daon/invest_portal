import asyncio
import io
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Asset
from app.services.market.history_service import get_history
from app.services.chart.chart_service import generate_ta_chart, to_weekly
from app.services.notification import telegram_service
from app.services.market.quote_service import get_quote
from app.services.ai import chart_analyzer
from app.services.ai.llm_client import LiteLLMError

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
    quote = await get_quote(asset)
    caption = f"<b>{asset.name}</b> ({asset.ticker}·{asset.market})\n현재가: {quote.price:,} {asset.currency}"
    images: list[tuple[bytes, str]] = []
    sent = 0
    try:
        for i, period in enumerate(("daily", "weekly")):
            if i > 0:
                await asyncio.sleep(1)   # 텔레그램 연속 사진 발송 rate limit(429) 회피
            png = await _build_png(db, asset_id, period)
            images.append((png, "image/png"))
            cap = f"{caption}\n[{period.upper()}]"
            if await telegram_service.send_photo(db, png, cap):
                sent += 1
    except telegram_service.TelegramNotConfigured as e:
        raise HTTPException(409, str(e))

    analysis_sent = False
    try:
        parts = await chart_analyzer.analyze(db, images, asset.ticker, asset.name, asset.market)
        for i, part in enumerate(parts):
            if i > 0:
                await asyncio.sleep(1)
            await telegram_service.send_message(db, part)
        analysis_sent = bool(parts)
    except (chart_analyzer.AnalysisDisabled, chart_analyzer.AnalysisNotConfigured):
        pass   # AI 미설정/비활성 → 차트만 발송
    except Exception as e:   # noqa: BLE001 — AI 실패가 차트 발송을 막지 않도록 best-effort
        logging.getLogger(__name__).warning("AI 분석 발송 실패(차트는 발송됨): %s", e)

    return {"sent": sent, "ok": sent > 0, "analysis_sent": analysis_sent}
