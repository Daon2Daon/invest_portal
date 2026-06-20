from typing import Literal
from pydantic import BaseModel, field_validator

Basis = Literal["ABSOLUTE", "PURCHASE_AVG", "WEEK52_HIGH", "WEEK52_LOW", "REFERENCE"]
Direction = Literal["ABOVE", "BELOW", "BOTH"]


class AlertCreate(BaseModel):
    asset_id: int
    basis: Basis
    direction: Direction
    value: float
    note: str | None = None

    @field_validator("value")
    @classmethod
    def _positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("value는 0보다 커야 합니다.")
        return v


class AlertUpdate(BaseModel):
    value: float | None = None
    direction: Direction | None = None
    note: str | None = None
    enabled: bool | None = None

    @field_validator("value")
    @classmethod
    def _positive(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("value는 0보다 커야 합니다.")
        return v


class AlertOut(BaseModel):
    alert_id: int
    asset_id: int
    basis: str
    direction: str
    value: float
    reference_price: float | None = None
    enabled: bool
    is_triggered: bool
    note: str | None = None

    model_config = {"from_attributes": True}
