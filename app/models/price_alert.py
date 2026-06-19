from datetime import datetime
from sqlalchemy import String, Boolean, Numeric, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class PriceAlert(Base):
    __tablename__ = "price_alerts"

    alert_id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False, index=True)
    basis: Mapped[str] = mapped_column(String, nullable=False)       # ABSOLUTE/PURCHASE_AVG/WEEK52_HIGH/WEEK52_LOW
    direction: Mapped[str] = mapped_column(String, nullable=False)   # ABOVE/BELOW
    value: Mapped[float] = mapped_column(Numeric, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_triggered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
