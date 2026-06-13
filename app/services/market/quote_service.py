import asyncio
from app.services.market.types import Quote
from app.services.market.registry import registry


async def get_quote(asset) -> Quote:
    """ORM Asset 객체를 받아 data_source에 맞는 provider로 시세를 조회한다(블로킹 → 스레드)."""
    provider = registry.for_source(asset.data_source)
    if asset.data_source == "manual":
        return await asyncio.to_thread(
            provider.quote, asset.fetch_symbol, asset.currency, asset.asset_type, asset.manual_price
        )
    return await asyncio.to_thread(
        provider.quote, asset.fetch_symbol, asset.currency, asset.asset_type
    )
