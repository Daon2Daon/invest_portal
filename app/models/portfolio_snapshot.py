from datetime import datetime, date
from sqlalchemy import Numeric, Date, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    total_value_krw: Mapped[float] = mapped_column(Numeric, nullable=False)
    total_cost_krw: Mapped[float] = mapped_column(Numeric, nullable=False)
    total_pl_krw: Mapped[float] = mapped_column(Numeric, nullable=False)
    total_cash_krw: Mapped[float] = mapped_column(Numeric, nullable=False)
    allocation: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
