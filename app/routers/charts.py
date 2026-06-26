import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Asset
from app.services.chart.chart_builder import build_png, ChartDataError
from app.services.notification import telegram_service, chart_dispatch
from app.services.ai import chart_analyzer
from app.services.ai import analysis_store
from app.services.ai.llm_client import LiteLLMError
import re
from pydantic import BaseModel, field_validator
from app.services.scheduler import schedule_store
from app.services.scheduler.schedule_store import FEATURE_CHART

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
        text, model = await chart_analyzer.analyze_raw(db, images, asset.ticker, asset.name, asset.market)
    except (chart_analyzer.AnalysisDisabled, chart_analyzer.AnalysisNotConfigured) as e:
        raise HTTPException(409, str(e))
    except LiteLLMError as e:
        raise HTTPException(502, str(e))
    row = await analysis_store.create_and_prune(db, asset_id, text, model, trigger="manual")
    return {"analysis": text, "id": row.id, "created_at": row.created_at}


@router.get("/{asset_id}/analyses")
async def list_analyses(asset_id: int, limit: int = Query(20, ge=1, le=100),
                        db: AsyncSession = Depends(get_db)):
    rows = await analysis_store.list_for_asset(db, asset_id, limit=limit)
    return [
        {"id": r.id, "asset_id": r.asset_id, "content_md": r.content_md,
         "model": r.model, "trigger": r.trigger, "created_at": r.created_at}
        for r in rows
    ]


@router.delete("/analyses/{analysis_id}")
async def delete_analysis(analysis_id: int, db: AsyncSession = Depends(get_db)):
    if not await analysis_store.delete(db, analysis_id):
        raise HTTPException(404, "analysis not found")
    return {"ok": True}


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


class ScheduleIn(BaseModel):
    send_time: str          # "HH:MM"
    days_of_week: list[int]  # 0(월)~6(일)
    enabled: bool = True

    @field_validator("send_time")
    @classmethod
    def _valid_time(cls, v: str) -> str:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("send_time은 HH:MM 형식이어야 합니다.")
        return v

    @field_validator("days_of_week")
    @classmethod
    def _valid_days(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("days_of_week는 0~6 정수여야 합니다.")
        return v


@router.get("/{asset_id}/schedule")
async def get_schedule(asset_id: int, db: AsyncSession = Depends(get_db)):
    sched = await schedule_store.get_schedule(db, FEATURE_CHART, asset_id)
    if sched is None:
        return None
    return {
        "send_time": sched.send_time,
        "days_of_week": [int(x) for x in sched.days_of_week.split(",") if x != ""],
        "enabled": sched.enabled,
    }


@router.put("/{asset_id}/schedule")
async def put_schedule(asset_id: int, body: ScheduleIn, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    days = ",".join(str(d) for d in sorted(set(body.days_of_week)))
    await schedule_store.upsert_schedule(db, FEATURE_CHART, asset_id, body.send_time, days, body.enabled)
    return {"status": "ok"}


@router.delete("/{asset_id}/schedule")
async def delete_schedule(asset_id: int, db: AsyncSession = Depends(get_db)):
    await schedule_store.delete_schedule(db, FEATURE_CHART, asset_id)
    return {"status": "ok"}
