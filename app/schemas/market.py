from pydantic import BaseModel


class ResolveRequest(BaseModel):
    ticker: str
    market: str
    asset_type: str | None = None


class ResolvedAssetOut(BaseModel):
    ticker: str
    name: str
    asset_type: str
    market: str
    currency: str
    data_source: str
    fetch_symbol: str
    current_price: float | None = None
    name_en: str | None = None


class ResolveResponse(BaseModel):
    ok: bool
    asset: ResolvedAssetOut | None = None
    tried: list[str] = []
    suggestion: str = ""
