from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset
from app.services.market.quote_service import get_quote
from app.services.portfolio.portfolio_service import held_asset_ids


async def get_watchlist(db: AsyncSession) -> list[dict]:
    """관심종목(보유 lot 없는 활성 자산) + 라이브 시세 목록.
    시세 조회 실패(status!=ok) 시 current_price는 None으로 두되 목록에는 유지한다."""
    held = await held_asset_ids(db)
    assets = (await db.execute(
        select(Asset).where(Asset.is_active == True)  # noqa: E712
    )).scalars().all()
    out: list[dict] = []
    for a in assets:
        if a.asset_id in held:
            continue
        q = await get_quote(a)
        out.append({
            "asset_id": a.asset_id, "ticker": a.ticker, "name": a.name,
            "market": a.market, "currency": a.currency, "asset_type": a.asset_type,
            "asset_class": a.asset_class,
            "current_price": q.price if q.status == "ok" else None,
            "change": q.change, "change_pct": q.change_pct, "price_status": q.status,
        })
    return out
