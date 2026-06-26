import pytest
from sqlalchemy import select
from app.models.asset_ai_analysis import AssetAIAnalysis
from app.models.asset import Asset
from app.services.ai import analysis_store


async def _make_asset(db, ticker="005930"):
    a = Asset(ticker=ticker, name="삼성전자", asset_type="stock", market="KR",
              currency="KRW", data_source="pykrx", fetch_symbol=ticker)
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


@pytest.mark.asyncio
async def test_table_created(db_session):
    rows = (await db_session.execute(select(AssetAIAnalysis))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_create_and_list_newest_first(db_session):
    a = await _make_asset(db_session)
    r1 = await analysis_store.create_and_prune(db_session, a.asset_id, "## A", "m", "manual")
    r2 = await analysis_store.create_and_prune(db_session, a.asset_id, "## B", "m", "scheduled")
    rows = await analysis_store.list_for_asset(db_session, a.asset_id)
    assert [r.id for r in rows] == [r2.id, r1.id]
    assert rows[0].content_md == "## B"


@pytest.mark.asyncio
async def test_prune_keeps_only_n(db_session):
    a = await _make_asset(db_session)
    for i in range(23):
        await analysis_store.create_and_prune(db_session, a.asset_id, f"#{i}", "m", "manual", keep=20)
    rows = await analysis_store.list_for_asset(db_session, a.asset_id, limit=100)
    assert len(rows) == 20
    assert rows[0].content_md == "#22"   # 최신 유지
    assert all(r.content_md != "#0" for r in rows)  # 가장 오래된 것 삭제됨


@pytest.mark.asyncio
async def test_prune_isolated_per_asset(db_session):
    a = await _make_asset(db_session, "005930")
    b = await _make_asset(db_session, "000660")
    for i in range(22):
        await analysis_store.create_and_prune(db_session, a.asset_id, f"a{i}", "m", "manual", keep=20)
    await analysis_store.create_and_prune(db_session, b.asset_id, "b0", "m", "manual", keep=20)
    assert len(await analysis_store.list_for_asset(db_session, a.asset_id, limit=100)) == 20
    assert len(await analysis_store.list_for_asset(db_session, b.asset_id, limit=100)) == 1


@pytest.mark.asyncio
async def test_delete(db_session):
    a = await _make_asset(db_session)
    r = await analysis_store.create_and_prune(db_session, a.asset_id, "x", "m", "manual")
    assert await analysis_store.delete(db_session, r.id) is True
    assert await analysis_store.delete(db_session, 999999) is False
