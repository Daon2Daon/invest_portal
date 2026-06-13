from pydantic import BaseModel


class AssetCreate(BaseModel):
    ticker: str
    name: str
    asset_type: str
    market: str
    currency: str
    data_source: str
    fetch_symbol: str
    name_en: str | None = None


class ManualPriceUpdate(BaseModel):
    manual_price: float
    manual_price_currency: str


class AssetOut(BaseModel):
    asset_id: int
    ticker: str
    name: str
    asset_type: str
    market: str
    currency: str
    data_source: str
    fetch_symbol: str
    manual_price: float | None = None
    is_active: bool

    model_config = {"from_attributes": True}
