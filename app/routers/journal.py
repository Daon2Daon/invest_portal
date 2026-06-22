from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import JournalEntry, Asset
from app.schemas.journal import JournalCreate, JournalUpdate

router = APIRouter(prefix="/api/journal", tags=["journal"])
_KST = ZoneInfo("Asia/Seoul")


async def _asset_map(db: AsyncSession, asset_ids) -> dict:
    ids = {i for i in asset_ids if i is not None}
    if not ids:
        return {}
    rows = (await db.execute(select(Asset).where(Asset.asset_id.in_(ids)))).scalars().all()
    return {a.asset_id: (a.name, a.ticker) for a in rows}


def _serialize(e: JournalEntry, amap: dict) -> dict:
    name, ticker = amap.get(e.asset_id, (None, None))
    return {
        "id": e.id, "entry_date": e.entry_date.isoformat(),
        "title": e.title, "body": e.body, "asset_id": e.asset_id,
        "asset_name": name, "asset_ticker": ticker,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


async def _validate_asset(db: AsyncSession, asset_id) -> None:
    if asset_id is not None and await db.get(Asset, asset_id) is None:
        raise HTTPException(422, "연결할 종목을 찾을 수 없습니다.")


@router.post("")
async def create_entry(body: JournalCreate, db: AsyncSession = Depends(get_db)):
    if not body.title or not body.title.strip():
        raise HTTPException(422, "title은 비울 수 없습니다.")
    await _validate_asset(db, body.asset_id)
    entry = JournalEntry(
        entry_date=body.entry_date or datetime.now(_KST).date(),
        title=body.title, body=body.body, asset_id=body.asset_id)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _serialize(entry, await _asset_map(db, [entry.asset_id]))


@router.get("")
async def list_entries(asset_id: int | None = Query(None), db: AsyncSession = Depends(get_db)):
    stmt = select(JournalEntry).order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
    if asset_id is not None:
        stmt = stmt.where(JournalEntry.asset_id == asset_id)
    entries = (await db.execute(stmt)).scalars().all()
    amap = await _asset_map(db, [e.asset_id for e in entries])
    return [_serialize(e, amap) for e in entries]


@router.get("/{entry_id}")
async def get_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    e = await db.get(JournalEntry, entry_id)
    if e is None:
        raise HTTPException(404, "저널 항목을 찾을 수 없습니다.")
    return _serialize(e, await _asset_map(db, [e.asset_id]))


@router.put("/{entry_id}")
async def update_entry(entry_id: int, body: JournalUpdate, db: AsyncSession = Depends(get_db)):
    e = await db.get(JournalEntry, entry_id)
    if e is None:
        raise HTTPException(404, "저널 항목을 찾을 수 없습니다.")
    data = body.model_dump(exclude_unset=True)
    if "title" in data and (not data["title"] or not data["title"].strip()):
        raise HTTPException(422, "title은 비울 수 없습니다.")
    if "asset_id" in data:
        await _validate_asset(db, data["asset_id"])
    for k, v in data.items():
        setattr(e, k, v)
    await db.commit()
    await db.refresh(e)
    return _serialize(e, await _asset_map(db, [e.asset_id]))


@router.delete("/{entry_id}")
async def delete_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    e = await db.get(JournalEntry, entry_id)
    if e is None:
        raise HTTPException(404, "저널 항목을 찾을 수 없습니다.")
    await db.delete(e)
    await db.commit()
    return {"deleted": entry_id}
