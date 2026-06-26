"""feature_type별 발송 핸들러 + 레지스트리. 새 발송 기능은 여기 핸들러를 추가한다."""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, Schedule
from app.services.notification import chart_dispatch
from app.services.market.market_hours import is_trading_day
from app.services.market_summary import summary_service
from app.services.notification import telegram_service
from app.services.ai_report import report_generator, report_dispatch
from app.services.scheduler.schedule_store import FEATURE_SUMMARY_US, FEATURE_SUMMARY_KR, FEATURE_REPORT, FEATURE_RISK
from app.services.risk_signal import risk_service

_log = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")


async def handle_chart_analysis(db: AsyncSession, schedule: Schedule) -> None:
    asset = await db.get(Asset, schedule.target_id)
    if asset is None:
        _log.warning("스케줄 대상 asset 없음 target_id=%s", schedule.target_id)
        return
    await chart_dispatch.send_chart_telegram(db, asset, trigger="scheduled")


async def handle_market_summary(db: AsyncSession, schedule: Schedule) -> None:
    market = "US" if schedule.feature_type == FEATURE_SUMMARY_US else "KR"
    if not is_trading_day(market, datetime.now(_KST)):
        _log.info("증시 요약 휴장일 스킵 market=%s", market)
        return
    try:
        await summary_service.build_and_send(db, market)
    except telegram_service.TelegramNotConfigured:
        _log.info("텔레그램 미설정 — 증시 요약 발송 생략")


async def handle_ai_report(db: AsyncSession, schedule: Schedule) -> None:
    report = await report_generator.create_report(db, trigger="scheduled")
    try:
        await report_dispatch.send_report(db, report)
    except telegram_service.TelegramNotConfigured:
        _log.info("텔레그램 미설정 — AI 리포트 발송 생략(생성·저장은 완료)")


async def handle_risk_signal(db: AsyncSession, schedule: Schedule) -> None:
    cfg = await risk_service.load_config(db)
    if not cfg["enabled"]:
        _log.info("위험신호 비활성 — 자동 발송 스킵")
        return
    try:
        await risk_service.build_and_send(db)
    except telegram_service.TelegramNotConfigured:
        _log.info("텔레그램 미설정 — 위험신호 발송 생략")


HANDLERS = {
    "chart_analysis": handle_chart_analysis,
    FEATURE_SUMMARY_US: handle_market_summary,
    FEATURE_SUMMARY_KR: handle_market_summary,
    FEATURE_REPORT: handle_ai_report,
    FEATURE_RISK: handle_risk_signal,
}
