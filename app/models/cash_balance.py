from datetime import datetime
from sqlalchemy import String, Numeric, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CashBalance(Base):
    __tablename__ = "cash_balances"

    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[str] = mapped_column(String, nullable=False)   # KRW/USD/JPY 등
    amount: Mapped[float] = mapped_column(Numeric, nullable=False)
    label: Mapped[str | None] = mapped_column(String)              # "증권사 예수금" 등
    memo: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
