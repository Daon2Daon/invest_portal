import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.scheduler import schedule_store
from app.services.scheduler.schedule_store import FEATURE_SUMMARY_US, FEATURE_SUMMARY_KR
from app.services.market_summary import summary_service
from app.services.notification import telegram_service

router = APIRouter(prefix="/api/market-summary", tags=["market-summary"])

_FEATURE = {"US": FEATURE_SUMMARY_US, "KR": FEATURE_SUMMARY_KR}


def _feature(market: str) -> str:
    f = _FEATURE.get(market)
    if f is None:
        raise HTTPException(404, "market은 US 또는 KR이어야 합니다.")
    return f


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


@router.get("/{market}/schedule")
async def get_schedule(market: str, db: AsyncSession = Depends(get_db)):
    sched = await schedule_store.get_schedule(db, _feature(market), 0)
    if sched is None:
        return None
    return {
        "send_time": sched.send_time,
        "days_of_week": [int(x) for x in sched.days_of_week.split(",") if x != ""],
        "enabled": sched.enabled,
    }


@router.put("/{market}/schedule")
async def put_schedule(market: str, body: ScheduleIn, db: AsyncSession = Depends(get_db)):
    feature = _feature(market)
    days = ",".join(str(d) for d in sorted(set(body.days_of_week)))
    await schedule_store.upsert_schedule(db, feature, 0, body.send_time, days, body.enabled)
    return {"status": "ok"}


@router.delete("/{market}/schedule")
async def delete_schedule(market: str, db: AsyncSession = Depends(get_db)):
    await schedule_store.delete_schedule(db, _feature(market), 0)
    return {"status": "ok"}


@router.post("/{market}/send")
async def send_now(market: str, db: AsyncSession = Depends(get_db)):
    _feature(market)  # market 검증
    try:
        return await summary_service.build_and_send(db, market)
    except telegram_service.TelegramNotConfigured as e:
        raise HTTPException(409, str(e))
