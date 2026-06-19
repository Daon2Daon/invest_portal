"""지수 + 그 시장 보유/관심 종목 통계를 모아 텔레그램으로 발송."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset
from app.services.portfolio.portfolio_service import held_asset_ids
from app.services.market_summary.indices import index_lines
from app.services.market_summary.changes import asset_stats
from app.services.market_summary.message import build_message
from app.services.notification import telegram_service


async def build_and_send(db: AsyncSession, market: str) -> dict:
    indices = await index_lines(market)
    held = await held_asset_ids(db)
    assets = (await db.execute(
        select(Asset).where(Asset.is_active == True, Asset.market == market)  # noqa: E712
    )).scalars().all()
    holdings, watch = [], []
    for a in assets:
        s = await asset_stats(a)
        if s is None:
            continue
        row = (a.name, a.ticker, s)
        (holdings if a.asset_id in held else watch).append(row)
    msg = build_message(market, indices, holdings, watch)
    sent = await telegram_service.send_message(db, msg)
    return {"market": market, "sent": bool(sent),
            "indices": len(indices), "holdings": len(holdings), "watchlist": len(watch)}
