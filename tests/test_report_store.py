import pytest
from sqlalchemy import select
from app.models.ai_report import AIReport
from app.services.ai_report import report_store


@pytest.mark.asyncio
async def test_ai_reports_table_created(db_session):
    # db_session fixture가 create_all 하므로 빈 조회가 에러 없이 동작하면 테이블 생성됨
    rows = (await db_session.execute(select(AIReport))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_create_and_list_and_get_and_delete(db_session):
    r1 = await report_store.create(db_session, "리포트A", "## 본문A", "gemini/x", "manual")
    r2 = await report_store.create(db_session, "리포트B", "## 본문B", "gemini/x", "scheduled")
    rows = await report_store.list_reports(db_session)
    assert [r.id for r in rows][:2] == [r2.id, r1.id]   # 최신순
    got = await report_store.get_report(db_session, r1.id)
    assert got is not None and got.content_md == "## 본문A"
    assert await report_store.delete_report(db_session, r1.id) is True
    assert await report_store.get_report(db_session, r1.id) is None
    assert await report_store.delete_report(db_session, 999999) is False
