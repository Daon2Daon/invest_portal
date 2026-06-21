"""ai_reports 테이블 CRUD."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIReport


async def create(db: AsyncSession, title: str, content_md: str,
                 model: str, trigger: str) -> AIReport:
    row = AIReport(title=title, content_md=content_md, model=model, trigger=trigger)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_reports(db: AsyncSession, limit: int = 100) -> list[AIReport]:
    res = await db.execute(
        select(AIReport).order_by(AIReport.id.desc()).limit(limit)
    )
    return list(res.scalars().all())


async def get_report(db: AsyncSession, report_id: int) -> AIReport | None:
    return await db.get(AIReport, report_id)


async def delete_report(db: AsyncSession, report_id: int) -> bool:
    row = await db.get(AIReport, report_id)
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True
