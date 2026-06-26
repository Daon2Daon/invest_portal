"""asset_ai_analyses 테이블 CRUD. 종목당 최신 KEEP건만 유지."""
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_ai_analysis import AssetAIAnalysis

KEEP_DEFAULT = 20


async def create_and_prune(db: AsyncSession, asset_id: int, content_md: str,
                           model: str, trigger: str,
                           keep: int = KEEP_DEFAULT) -> AssetAIAnalysis:
    row = AssetAIAnalysis(asset_id=asset_id, content_md=content_md,
                          model=model, trigger=trigger)
    db.add(row)
    await db.commit()
    await db.refresh(row)

    # 같은 종목에서 최신 keep건만 남기고 나머지 삭제(id 내림차순 = 최신순).
    keep_ids = (await db.execute(
        select(AssetAIAnalysis.id)
        .where(AssetAIAnalysis.asset_id == asset_id)
        .order_by(AssetAIAnalysis.id.desc())
        .limit(keep)
    )).scalars().all()
    await db.execute(
        sa_delete(AssetAIAnalysis)
        .where(AssetAIAnalysis.asset_id == asset_id)
        .where(AssetAIAnalysis.id.notin_(keep_ids))
    )
    await db.commit()
    return row


async def list_for_asset(db: AsyncSession, asset_id: int,
                         limit: int = KEEP_DEFAULT) -> list[AssetAIAnalysis]:
    res = await db.execute(
        select(AssetAIAnalysis)
        .where(AssetAIAnalysis.asset_id == asset_id)
        .order_by(AssetAIAnalysis.id.desc())
        .limit(limit)
    )
    return list(res.scalars().all())


async def delete(db: AsyncSession, analysis_id: int) -> bool:
    row = await db.get(AssetAIAnalysis, analysis_id)
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True
