import pytest
from sqlalchemy import select
from app.models import Schedule


@pytest.mark.asyncio
async def test_schedules_table_created(db_session):
    # db_session fixture가 create_all 하므로 빈 조회가 에러 없이 동작하면 테이블 생성됨
    rows = (await db_session.execute(select(Schedule))).scalars().all()
    assert rows == []
