import os
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.pool import NullPool
from app.models import JournalEntry
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db import get_db
from app.models import Asset
from app.config import settings

_TEST_URL = os.environ.get("TEST_DATABASE_URL") or settings.TEST_DATABASE_URL


async def _test_get_db():
    """HTTP 요청마다 독립 연결을 사용하도록 NullPool 엔진으로 세션 생성."""
    engine = create_async_engine(_TEST_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as session:
            yield session
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def _override_get_db():
    """저널 API 테스트 동안만 get_db를 테스트 DB 세션으로 오버라이드(끝나면 원복).
    모듈 전역 오버라이드는 다른 테스트 파일로 누수되므로 fixture로 set/pop 한다."""
    app.dependency_overrides[get_db] = _test_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_journal_entries_table_created(db_session):
    # db_session fixture가 create_all 하므로 빈 조회가 에러 없이 동작하면 테이블 생성됨
    rows = (await db_session.execute(select(JournalEntry))).scalars().all()
    assert rows == []


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _mk_asset() -> Asset:
    return Asset(ticker="TST", name="테스트종목", asset_type="stock",
                 market="KR", currency="KRW", data_source="manual", fetch_symbol="TST")


@pytest.mark.asyncio
async def test_create_defaults_date_and_lists_newest_first(db_session):
    async with await _client() as ac:
        r1 = await ac.post("/api/journal", json={"title": "첫 메모", "body": "본문1"})
        r2 = await ac.post("/api/journal", json={"title": "둘째", "entry_date": "2020-01-01"})
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["title"] == "첫 메모" and body1["asset_id"] is None
    assert body1["entry_date"]
    async with await _client() as ac:
        lst = (await ac.get("/api/journal")).json()
    assert [e["title"] for e in lst][:2] == ["첫 메모", "둘째"]


@pytest.mark.asyncio
async def test_create_with_asset_enriches_name(db_session):
    a = _mk_asset()
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    async with await _client() as ac:
        r = await ac.post("/api/journal", json={"title": "종목메모", "asset_id": a.asset_id})
    body = r.json()
    assert body["asset_id"] == a.asset_id
    assert body["asset_name"] == "테스트종목" and body["asset_ticker"] == "TST"


@pytest.mark.asyncio
async def test_create_empty_title_422():
    async with await _client() as ac:
        r = await ac.post("/api/journal", json={"title": "   "})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_invalid_asset_422(db_session):
    async with await _client() as ac:
        r = await ac.post("/api/journal", json={"title": "x", "asset_id": 999999})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_filter_by_asset(db_session):
    a = _mk_asset()
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    async with await _client() as ac:
        await ac.post("/api/journal", json={"title": "연결", "asset_id": a.asset_id})
        await ac.post("/api/journal", json={"title": "비연결"})
        filtered = (await ac.get(f"/api/journal?asset_id={a.asset_id}")).json()
    assert [e["title"] for e in filtered] == ["연결"]


@pytest.mark.asyncio
async def test_update_partial_and_clear_asset(db_session):
    a = _mk_asset()
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    async with await _client() as ac:
        created = (await ac.post("/api/journal", json={"title": "원본", "asset_id": a.asset_id})).json()
        upd = (await ac.put(f"/api/journal/{created['id']}",
                            json={"title": "수정됨", "asset_id": None})).json()
    assert upd["title"] == "수정됨" and upd["asset_id"] is None and upd["asset_name"] is None


@pytest.mark.asyncio
async def test_get_and_delete_and_404(db_session):
    async with await _client() as ac:
        created = (await ac.post("/api/journal", json={"title": "삭제대상"})).json()
        got = await ac.get(f"/api/journal/{created['id']}")
        assert got.status_code == 200
        dele = await ac.delete(f"/api/journal/{created['id']}")
        assert dele.status_code == 200
        assert (await ac.get(f"/api/journal/{created['id']}")).status_code == 404
        assert (await ac.put(f"/api/journal/{created['id']}", json={"title": "x"})).status_code == 404
        assert (await ac.delete(f"/api/journal/{created['id']}")).status_code == 404


@pytest.mark.asyncio
async def test_asset_delete_sets_null(db_session):
    a = _mk_asset()
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    async with await _client() as ac:
        created = (await ac.post("/api/journal", json={"title": "보존", "asset_id": a.asset_id})).json()
    await db_session.delete(a)
    await db_session.commit()
    async with await _client() as ac:
        got = (await ac.get(f"/api/journal/{created['id']}")).json()
    assert got["asset_id"] is None and got["title"] == "보존"
