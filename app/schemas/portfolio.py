from pydantic import BaseModel


class Position(BaseModel):
    asset_id: int
    ticker: str
    name: str
    market: str
    currency: str
    asset_class: str
    quantity: float
    avg_price: float
    current_price: float
    cost_native: float
    value_native: float
    profit_loss_native: float
    cost_krw: float
    value_krw: float
    profit_loss_krw: float
    profit_loss_pct: float
    weight_pct: float
    price_status: str


class CashPosition(BaseModel):
    id: int
    currency: str
    amount: float
    label: str | None = None
    value_krw: float
    weight_pct: float


class AllocationSlice(BaseModel):
    asset_class: str
    value_krw: float
    weight_pct: float


class PortfolioSummary(BaseModel):
    total_value_krw: float
    total_cost_krw: float
    total_profit_loss_krw: float
    total_profit_loss_pct: float
    total_cash_krw: float


class PortfolioOut(BaseModel):
    positions: list[Position]
    cash: list[CashPosition]
    allocation: list[AllocationSlice]
    summary: PortfolioSummary
