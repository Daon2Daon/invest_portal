import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.ai_report import report_generator, report_store, report_dispatch
from app.services.ai.llm_client import LiteLLMError
from app.services.notification import telegram_service
from app.services.scheduler import schedule_store
from app.services.scheduler.schedule_store import FEATURE_REPORT

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _serialize(r) -> dict:
    return {"id": r.id, "title": r.title, "content_md": r.content_md,
            "model": r.model, "trigger": r.trigger,
            "created_at": r.created_at.isoformat() if r.created_at else None}


@router.post("")
async def create_report(db: AsyncSession = Depends(get_db)):
    try:
        report = await report_generator.create_report(db, trigger="manual")
    except (report_generator.ReportDisabled, report_generator.ReportNotConfigured) as e:
        raise HTTPException(409, str(e))
    except LiteLLMError as e:
        raise HTTPException(502, str(e))
    return _serialize(report)


@router.get("")
async def list_reports(db: AsyncSession = Depends(get_db)):
    rows = await report_store.list_reports(db)
    return [_serialize(r) for r in rows]


class ScheduleIn(BaseModel):
    send_time: str
    days_of_week: list[int]
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


@router.get("/schedule")
async def get_schedule(db: AsyncSession = Depends(get_db)):
    sched = await schedule_store.get_schedule(db, FEATURE_REPORT, 0)
    if sched is None:
        return None
    return {"send_time": sched.send_time,
            "days_of_week": [int(x) for x in sched.days_of_week.split(",") if x != ""],
            "enabled": sched.enabled}


@router.put("/schedule")
async def put_schedule(body: ScheduleIn, db: AsyncSession = Depends(get_db)):
    days = ",".join(str(d) for d in sorted(set(body.days_of_week)))
    await schedule_store.upsert_schedule(db, FEATURE_REPORT, 0, body.send_time, days, body.enabled)
    return {"status": "ok"}


@router.delete("/schedule")
async def delete_schedule(db: AsyncSession = Depends(get_db)):
    await schedule_store.delete_schedule(db, FEATURE_REPORT, 0)
    return {"status": "ok"}


@router.get("/{report_id}")
async def get_report(report_id: int, db: AsyncSession = Depends(get_db)):
    r = await report_store.get_report(db, report_id)
    if r is None:
        raise HTTPException(404, "리포트를 찾을 수 없습니다.")
    return _serialize(r)


@router.delete("/{report_id}")
async def delete_report(report_id: int, db: AsyncSession = Depends(get_db)):
    await report_store.delete_report(db, report_id)
    return {"status": "ok"}


@router.post("/{report_id}/send-telegram")
async def send_telegram(report_id: int, db: AsyncSession = Depends(get_db)):
    r = await report_store.get_report(db, report_id)
    if r is None:
        raise HTTPException(404, "리포트를 찾을 수 없습니다.")
    try:
        sent = await report_dispatch.send_report(db, r)
    except telegram_service.TelegramNotConfigured as e:
        raise HTTPException(409, str(e))
    return {"sent": sent}
