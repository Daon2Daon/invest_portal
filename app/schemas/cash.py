from pydantic import BaseModel


class CashCreate(BaseModel):
    currency: str
    amount: float
    label: str | None = None
    memo: str | None = None


class CashUpdate(BaseModel):
    currency: str | None = None
    amount: float | None = None
    label: str | None = None
    memo: str | None = None


class CashOut(BaseModel):
    id: int
    currency: str
    amount: float
    label: str | None = None
    memo: str | None = None

    model_config = {"from_attributes": True}
