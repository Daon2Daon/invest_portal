import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.settings.settings_manager import set_setting
from app.services.risk_signal import risk_service
from app.services.scheduler import schedule_store
from app.services.scheduler.schedule_store import FEATURE_RISK
from app.services.notification import telegram_service

router = APIRouter(prefix="/api/risk-signal", tags=["risk-signal"])

CATEGORY = "risk_signal"
_BOOL_KEYS = ("enabled", "sig_rsi", "sig_macd", "sig_bollinger", "sig_ma",
              "sig_concentration_asset", "sig_concentration_class")
_FLOAT_KEYS = ("threshold_asset_pct", "threshold_class_pct")


class SettingsIn(BaseModel):
    enabled: bool | None = None
    sig_rsi: bool | None = None
    sig_macd: bool | None = None
    sig_bollinger: bool | None = None
    sig_ma: bool | None = None
    sig_concentration_asset: bool | None = None
    sig_concentration_class: bool | None = None
    threshold_asset_pct: float | None = None
    threshold_class_pct: float | None = None


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


@router.get("/settings")
async def get_settings(db: AsyncSession = Depends(get_db)):
    return await risk_service.load_config(db)


@router.put("/settings")
async def put_settings(body: SettingsIn, db: AsyncSession = Depends(get_db)):
    for key in _BOOL_KEYS:
        v = getattr(body, key)
        if v is not None:
            await set_setting(db, CATEGORY, key, "true" if v else "false", is_secret=False)
    for key in _FLOAT_KEYS:
        v = getattr(body, key)
        if v is not None:
            await set_setting(db, CATEGORY, key, str(float(v)), is_secret=False)
    return {"status": "ok"}


@router.get("/schedule")
async def get_schedule(db: AsyncSession = Depends(get_db)):
    sched = await schedule_store.get_schedule(db, FEATURE_RISK, 0)
    if sched is None:
        return None
    return {"send_time": sched.send_time,
            "days_of_week": [int(x) for x in sched.days_of_week.split(",") if x != ""],
            "enabled": sched.enabled}


@router.put("/schedule")
async def put_schedule(body: ScheduleIn, db: AsyncSession = Depends(get_db)):
    days = ",".join(str(d) for d in sorted(set(body.days_of_week)))
    await schedule_store.upsert_schedule(db, FEATURE_RISK, 0, body.send_time, days, body.enabled)
    return {"status": "ok"}


@router.delete("/schedule")
async def delete_schedule(db: AsyncSession = Depends(get_db)):
    await schedule_store.delete_schedule(db, FEATURE_RISK, 0)
    return {"status": "ok"}


@router.post("/preview")
async def preview(db: AsyncSession = Depends(get_db)):
    return {"text": await risk_service.build_digest(db)}


@router.post("/send")
async def send(db: AsyncSession = Depends(get_db)):
    try:
        return await risk_service.build_and_send(db)
    except telegram_service.TelegramNotConfigured as e:
        raise HTTPException(409, str(e))
