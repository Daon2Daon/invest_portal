import os
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy import text

from app.db import Base
from app.config import settings

TEST_URL = os.environ.get("TEST_DATABASE_URL") or settings.TEST_DATABASE_URL


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """통합 테스트용 세션. TEST_DATABASE_URL 미설정 시 skip."""
    if not TEST_URL:
        pytest.skip("TEST_DATABASE_URL 미설정 — DB 통합 테스트 skip")
    engine = create_async_engine(TEST_URL)
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {settings.SCHEMA_NAME}"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()
