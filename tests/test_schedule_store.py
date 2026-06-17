import pytest
from sqlalchemy import select
from app.models import Schedule
from app.services.scheduler import schedule_store as store
from app.services.scheduler.schedule_store import FEATURE_CHART


@pytest.mark.asyncio
async def test_schedules_table_created(db_session):
    # db_session fixture가 create_all 하므로 빈 조회가 에러 없이 동작하면 테이블 생성됨
    rows = (await db_session.execute(select(Schedule))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_upsert_creates_then_updates(db_session):
    s1 = await store.upsert_schedule(db_session, FEATURE_CHART, 1, "08:30", "0,1,2", True)
    assert s1.schedule_id is not None
    assert s1.send_time == "08:30"
    # 같은 (feature,target) 재호출 → update(중복 생성 X, UNIQUE)
    s2 = await store.upsert_schedule(db_session, FEATURE_CHART, 1, "09:00", "0,1,2,3,4", False)
    assert s2.schedule_id == s1.schedule_id
    assert s2.send_time == "09:00"
    assert s2.enabled is False
    all_rows = await store.list_enabled(db_session)
    assert all_rows == []  # enabled=False라 비활성 목록엔 없음


@pytest.mark.asyncio
async def test_get_and_delete(db_session):
    await store.upsert_schedule(db_session, FEATURE_CHART, 2, "10:00", "5,6", True)
    got = await store.get_schedule(db_session, FEATURE_CHART, 2)
    assert got is not None and got.target_id == 2
    assert await store.delete_schedule(db_session, FEATURE_CHART, 2) is True
    assert await store.get_schedule(db_session, FEATURE_CHART, 2) is None
    assert await store.delete_schedule(db_session, FEATURE_CHART, 2) is False  # 이미 없음


@pytest.mark.asyncio
async def test_list_enabled_only_returns_enabled(db_session):
    await store.upsert_schedule(db_session, FEATURE_CHART, 3, "08:00", "0", True)
    await store.upsert_schedule(db_session, FEATURE_CHART, 4, "08:00", "0", False)
    enabled = await store.list_enabled(db_session)
    targets = {s.target_id for s in enabled}
    assert 3 in targets and 4 not in targets
