from datetime import datetime, date
from sqlalchemy import String, Boolean, Integer, Date, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class Schedule(Base):
    __tablename__ = "schedules"
    __table_args__ = (
        UniqueConstraint("feature_type", "target_id", name="uq_schedules_feature_target"),
    )

    schedule_id: Mapped[int] = mapped_column(primary_key=True)
    feature_type: Mapped[str] = mapped_column(String, nullable=False)   # 예: "chart_analysis"
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)     # chart_analysis면 asset_id
    send_time: Mapped[str] = mapped_column(String, nullable=False)      # "HH:MM" KST 벽시계
    days_of_week: Mapped[str] = mapped_column(String, nullable=False)   # "0,1,2,3,4" (월=0…일=6)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_date: Mapped[date | None] = mapped_column(Date)            # 마지막 발송 KST 날짜
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
