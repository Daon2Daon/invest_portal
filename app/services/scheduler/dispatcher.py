"""1분 tick: due 스케줄을 순차 발송. _is_due는 순수 함수(테스트 대상)."""
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.db import SessionLocal
from app.models import Schedule
from app.services.scheduler import schedule_store
from app.services.scheduler.handlers import HANDLERS

_KST = ZoneInfo("Asia/Seoul")
_log = logging.getLogger(__name__)


def _parse_days(days_of_week: str) -> set[int]:
    out: set[int] = set()
    for tok in days_of_week.split(","):
        tok = tok.strip()
        if tok.isdigit():
            out.add(int(tok))
    return out


def _is_due(schedule: Schedule, now: datetime) -> bool:
    if not schedule.enabled:
        return False
    if now.weekday() not in _parse_days(schedule.days_of_week):
        return False
    hh, mm = schedule.send_time.split(":")
    if (now.hour, now.minute) < (int(hh), int(mm)):
        return False
    if schedule.last_run_date == now.date():
        return False
    return True


async def dispatch_tick() -> None:
    now = datetime.now(_KST)
    async with SessionLocal() as db:
        schedules = await schedule_store.list_enabled(db)
        due = [s for s in schedules if _is_due(s, now)]
        for i, sched in enumerate(due):
            if i > 0:
                await asyncio.sleep(2)   # 종목 간 발송 간격(텔레그램 rate limit 여유)
            handler = HANDLERS.get(sched.feature_type)
            if handler is None:
                _log.warning("미지의 feature_type=%s schedule_id=%s skip",
                             sched.feature_type, sched.schedule_id)
                continue
            try:
                await handler(db, sched)
                sched.last_run_date = now.date()
                await db.commit()
            except Exception as e:   # noqa: BLE001 — 한 건 실패가 나머지를 막지 않게
                await db.rollback()
                _log.warning("스케줄 발송 실패 schedule_id=%s: %s", sched.schedule_id, e)
