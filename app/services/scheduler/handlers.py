"""feature_type별 발송 핸들러 + 레지스트리. 새 발송 기능은 여기 핸들러를 추가한다."""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, Schedule
from app.services.notification import chart_dispatch

_log = logging.getLogger(__name__)


async def handle_chart_analysis(db: AsyncSession, schedule: Schedule) -> None:
    asset = await db.get(Asset, schedule.target_id)
    if asset is None:
        _log.warning("스케줄 대상 asset 없음 target_id=%s", schedule.target_id)
        return
    await chart_dispatch.send_chart_telegram(db, asset)


HANDLERS = {"chart_analysis": handle_chart_analysis}
