from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Holding
from app.schemas.holding import HoldingCreate, HoldingUpdate, HoldingOut

router = APIRouter(prefix="/api/holdings", tags=["holdings"])


@router.post("", response_model=HoldingOut)
async def create_holding(body: HoldingCreate, db: AsyncSession = Depends(get_db)):
    h = Holding(**body.model_dump())
    db.add(h)
    await db.commit()
    await db.refresh(h)
    return h


@router.get("", response_model=list[HoldingOut])
async def list_holdings(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Holding))).scalars().all()


@router.put("/{holding_id}", response_model=HoldingOut)
async def update_holding(holding_id: int, body: HoldingUpdate, db: AsyncSession = Depends(get_db)):
    h = await db.get(Holding, holding_id)
    if h is None:
        raise HTTPException(404, "holding not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(h, k, v)
    await db.commit()
    await db.refresh(h)
    return h


@router.delete("/{holding_id}")
async def delete_holding(holding_id: int, db: AsyncSession = Depends(get_db)):
    h = await db.get(Holding, holding_id)
    if h is None:
        raise HTTPException(404, "holding not found")
    await db.delete(h)
    await db.commit()
    return {"deleted": holding_id}
