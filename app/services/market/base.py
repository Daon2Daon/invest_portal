from typing import Protocol
from app.services.market.types import ResolvedAsset, Quote


class PriceProvider(Protocol):
    def resolve(self, ticker: str, market: str, asset_type_hint: str | None = None) -> ResolvedAsset | None:
        ...

    def quote(self, fetch_symbol: str, currency: str, asset_type: str) -> Quote | None:
        ...
