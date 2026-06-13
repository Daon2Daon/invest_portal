from datetime import datetime, date
from sqlalchemy import String, Numeric, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class Holding(Base):
    __tablename__ = "holdings"

    holding_id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric, nullable=False)
    purchase_price: Mapped[float] = mapped_column(Numeric, nullable=False)
    purchase_fx_rate: Mapped[float | None] = mapped_column(Numeric)
    fee: Mapped[float] = mapped_column(Numeric, default=0)
    memo: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
