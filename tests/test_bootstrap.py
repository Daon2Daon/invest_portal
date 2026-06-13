import pytest
from sqlalchemy import text
from app.bootstrap import ensure_schema
from app.config import settings


@pytest.mark.asyncio
async def test_ensure_schema_is_idempotent(db_session):
    # 두 번 호출해도 예외가 없어야 한다.
    await ensure_schema(db_session.bind)
    await ensure_schema(db_session.bind)
    rows = await db_session.execute(text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema=:s"
    ), {"s": settings.SCHEMA_NAME})
    names = {r[0] for r in rows}
    assert {"assets", "exchange_rates", "price_snapshots", "holdings", "app_settings"} <= names
