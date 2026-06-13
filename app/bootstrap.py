from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db import Base
from app.config import settings
import app.models  # noqa: F401  — 모든 모델을 메타데이터에 등록


async def ensure_schema(engine: AsyncEngine) -> None:
    """invest 스키마와 모든 테이블을 멱등 생성한다."""
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {settings.SCHEMA_NAME}"))
        await conn.run_sync(Base.metadata.create_all)
