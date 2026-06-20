from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import PortfolioSnapshot


async def upsert_snapshot(db: AsyncSession, row: dict) -> PortfolioSnapshot:
    """date 기준 upsert. 같은 날짜 행이 있으면 값만 갱신(멱등)."""
    snap = (await db.execute(
        select(PortfolioSnapshot).where(PortfolioSnapshot.date == row["date"])
    )).scalar_one_or_none()
    if snap is None:
        snap = PortfolioSnapshot(date=row["date"])
        db.add(snap)
    snap.total_value_krw = row["total_value_krw"]
    snap.total_cost_krw = row["total_cost_krw"]
    snap.total_pl_krw = row["total_pl_krw"]
    snap.total_cash_krw = row["total_cash_krw"]
    snap.allocation = row["allocation"]
    await db.commit()
    await db.refresh(snap)
    return snap


async def list_snapshots(db: AsyncSession, since: date | None) -> list[PortfolioSnapshot]:
    """since 이상 날짜를 오름차순으로. since=None이면 전체."""
    stmt = select(PortfolioSnapshot).order_by(PortfolioSnapshot.date.asc())
    if since is not None:
        stmt = stmt.where(PortfolioSnapshot.date >= since)
    return list((await db.execute(stmt)).scalars().all())
