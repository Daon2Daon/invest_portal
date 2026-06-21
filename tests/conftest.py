import os
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy import text

from app.db import Base
from app.config import settings

TEST_URL = os.environ.get("TEST_DATABASE_URL") or settings.TEST_DATABASE_URL

# 스키마/테이블 재생성(drop+create)은 테스트 세션당 1회만 수행한다. 이후 각 테스트는
# TRUNCATE로 격리한다. 테스트마다 drop_all/create_all(DDL, ACCESS EXCLUSIVE 락)을
# 반복하면 공유 invest_test 스키마에서 락 경합으로 간헐 InvalidRequestError가 났다.
# TRUNCATE는 테이블을 비우고 시퀀스를 리셋(RESTART IDENTITY)하므로 기존 방식과
# 관측 상태(빈 테이블 + id 1부터)가 동일하면서 DDL 경합만 제거한다.
_schema_ready = False


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """통합 테스트용 세션. TEST_DATABASE_URL 미설정 시 skip.

    첫 호출에서 스키마를 한 번 재생성하고, 이후 호출은 모든 테이블을 TRUNCATE해
    각 테스트가 깨끗한 상태(빈 테이블, id 시퀀스 1부터)에서 시작하도록 한다.
    """
    global _schema_ready
    if not TEST_URL:
        pytest.skip("TEST_DATABASE_URL 미설정 — DB 통합 테스트 skip")
    engine = create_async_engine(TEST_URL)
    async with engine.begin() as conn:
        if not _schema_ready:
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {settings.SCHEMA_NAME}"))
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
            _schema_ready = True
        else:
            tables = ", ".join(f'{settings.SCHEMA_NAME}."{t.name}"'
                               for t in Base.metadata.sorted_tables)
            await conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as session:
            yield session
    finally:
        await engine.dispose()
