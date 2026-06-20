"""일별 포트폴리오 스냅샷: get_portfolio 결과를 테이블 행으로 변환·적재한다."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import SessionLocal
from app.models import PortfolioSnapshot
from app.services.portfolio.portfolio_service import get_portfolio
from app.services.snapshot import snapshot_store

_KST = ZoneInfo("Asia/Seoul")


def build_snapshot_row(portfolio: dict, today: date) -> dict:
    """get_portfolio() 반환 dict + 날짜 → portfolio_snapshots 컬럼 dict(순수)."""
    s = portfolio["summary"]
    return {
        "date": today,
        "total_value_krw": s["total_value_krw"],
        "total_cost_krw": s["total_cost_krw"],
        "total_pl_krw": s["total_profit_loss_krw"],
        "total_cash_krw": s["total_cash_krw"],
        "allocation": [
            {"asset_class": a["asset_class"], "value_krw": a["value_krw"]}
            for a in portfolio["allocation"]
        ],
    }


async def capture_daily_snapshot(db: AsyncSession) -> PortfolioSnapshot:
    """현재 포트폴리오를 오늘(KST) 스냅샷으로 적재(멱등)."""
    portfolio = await get_portfolio(db)
    today = datetime.now(_KST).date()
    row = build_snapshot_row(portfolio, today)
    return await snapshot_store.upsert_snapshot(db, row)


async def snapshot_tick() -> None:
    """스케줄러 콜백: 자체 세션을 열어 1회 적재."""
    async with SessionLocal() as db:
        await capture_daily_snapshot(db)
