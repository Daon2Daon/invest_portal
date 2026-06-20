from datetime import datetime
from sqlalchemy import Text, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class AIReport(Base):
    __tablename__ = "ai_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False, default="")
    trigger: Mapped[str] = mapped_column(String, nullable=False, default="manual")  # manual | scheduled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
