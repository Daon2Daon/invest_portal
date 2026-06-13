from pydantic import BaseModel


class Position(BaseModel):
    asset_id: int
    ticker: str
    name: str
    market: str
    currency: str
    quantity: float
    avg_price: float
    current_price: float
    cost_krw: float
    value_krw: float
    profit_loss_krw: float
    profit_loss_pct: float
    weight_pct: float
    price_status: str


class PortfolioSummary(BaseModel):
    total_value_krw: float
    total_cost_krw: float
    total_profit_loss_krw: float
    total_profit_loss_pct: float


class PortfolioOut(BaseModel):
    positions: list[Position]
    summary: PortfolioSummary
