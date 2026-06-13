from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData

from app.config import settings

# 모든 테이블을 invest 스키마에 귀속시킨다.
metadata_obj = MetaData(schema=settings.SCHEMA_NAME)


class Base(DeclarativeBase):
    metadata = metadata_obj


engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
