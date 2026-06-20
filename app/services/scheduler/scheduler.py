"""AsyncIOScheduler 래퍼. tick 잡 1개만 등록(메모리 잡스토어, 진실의 원천은 schedules 테이블)."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.services.scheduler.dispatcher import dispatch_tick
from app.services.alert.alert_dispatcher import evaluate_tick as alert_evaluate_tick
from app.services.snapshot.snapshot_service import snapshot_tick

_log = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None
_TICK_JOB_ID = "dispatch_tick"


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    _scheduler.add_job(dispatch_tick, "interval", minutes=1, id=_TICK_JOB_ID,
                       replace_existing=True, max_instances=1, coalesce=True)
    _scheduler.add_job(alert_evaluate_tick, "interval", minutes=5, id="alert_tick",
                       replace_existing=True, max_instances=1, coalesce=True)
    _scheduler.add_job(snapshot_tick, "cron", hour=6, minute=30, id="daily_snapshot",
                       replace_existing=True, max_instances=1, coalesce=True)
    _scheduler.start()
    _log.info("스케줄러 시작(tick 1분 + 알림 5분 + 스냅샷 매일 06:30)")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
