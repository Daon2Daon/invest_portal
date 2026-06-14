import asyncio
from app.services.market.registry import registry


async def get_history(asset, days: int):
    """자산의 data_source에 맞는 provider로 일봉 OHLCV(DataFrame)를 조회한다(블로킹 → 스레드).
    컬럼은 provider가 Open/High/Low/Close/Volume 으로 정규화해 반환한다. 없으면 None."""
    provider = registry.for_source(asset.data_source)
    return await asyncio.to_thread(provider.history, asset.fetch_symbol, asset.market, days)
