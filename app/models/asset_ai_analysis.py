from datetime import datetime
from sqlalchemy import Text, String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class AssetAIAnalysis(Base):
    __tablename__ = "asset_ai_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.asset_id", ondelete="CASCADE"), index=True, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False, default="")
    trigger: Mapped[str] = mapped_column(String, nullable=False, default="manual")  # manual | scheduled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
