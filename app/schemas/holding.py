from datetime import date
from pydantic import BaseModel


class HoldingCreate(BaseModel):
    asset_id: int
    purchase_date: date
    quantity: float
    purchase_price: float
    purchase_fx_rate: float | None = None
    fee: float = 0
    memo: str | None = None


class HoldingUpdate(BaseModel):
    purchase_date: date | None = None
    quantity: float | None = None
    purchase_price: float | None = None
    purchase_fx_rate: float | None = None
    fee: float | None = None
    memo: str | None = None


class HoldingOut(BaseModel):
    holding_id: int
    asset_id: int
    purchase_date: date
    quantity: float
    purchase_price: float
    purchase_fx_rate: float | None = None
    fee: float
    memo: str | None = None

    model_config = {"from_attributes": True}
