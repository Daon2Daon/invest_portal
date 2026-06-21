"""schedules 테이블 CRUD. 라우터·디스패처가 공유한다."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Schedule

FEATURE_CHART = "chart_analysis"
FEATURE_SUMMARY_US = "market_summary_us"
FEATURE_SUMMARY_KR = "market_summary_kr"
FEATURE_REPORT = "ai_report"
FEATURE_RISK = "risk_signal"


async def get_schedule(db: AsyncSession, feature_type: str, target_id: int) -> Schedule | None:
    res = await db.execute(
        select(Schedule).where(
            Schedule.feature_type == feature_type,
            Schedule.target_id == target_id,
        )
    )
    return res.scalar_one_or_none()


async def upsert_schedule(db: AsyncSession, feature_type: str, target_id: int,
                          send_time: str, days_of_week: str, enabled: bool) -> Schedule:
    sched = await get_schedule(db, feature_type, target_id)
    if sched is None:
        sched = Schedule(feature_type=feature_type, target_id=target_id)
        db.add(sched)
    sched.send_time = send_time
    sched.days_of_week = days_of_week
    sched.enabled = enabled
    await db.commit()
    await db.refresh(sched)
    return sched


async def delete_schedule(db: AsyncSession, feature_type: str, target_id: int) -> bool:
    sched = await get_schedule(db, feature_type, target_id)
    if sched is None:
        return False
    await db.delete(sched)
    await db.commit()
    return True


async def list_enabled(db: AsyncSession) -> list[Schedule]:
    res = await db.execute(select(Schedule).where(Schedule.enabled.is_(True)))
    return list(res.scalars().all())
