from datetime import date
from pydantic import BaseModel


class HoldingCreate(BaseModel):
    asset_id: int
    quantity: float
    purchase_price: float
    purchase_date: date | None = None
    fee: float = 0
    memo: str | None = None


class HoldingWithAssetCreate(BaseModel):
    # 자산 필드 (resolve 결과)
    ticker: str
    name: str
    asset_type: str
    market: str
    currency: str
    data_source: str
    fetch_symbol: str
    name_en: str | None = None
    # 보유 필드
    quantity: float
    purchase_price: float
    purchase_date: date | None = None
    fee: float = 0
    memo: str | None = None


class HoldingUpdate(BaseModel):
    quantity: float | None = None
    purchase_price: float | None = None
    purchase_date: date | None = None
    fee: float | None = None
    memo: str | None = None


class HoldingOut(BaseModel):
    holding_id: int
    asset_id: int
    quantity: float
    purchase_price: float
    purchase_date: date | None = None
    fee: float
    memo: str | None = None

    model_config = {"from_attributes": True}
