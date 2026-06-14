from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import CashBalance
from app.schemas.cash import CashCreate, CashUpdate, CashOut

router = APIRouter(prefix="/api/cash", tags=["cash"])


@router.post("", response_model=CashOut)
async def create_cash(body: CashCreate, db: AsyncSession = Depends(get_db)):
    if body.amount < 0:
        raise HTTPException(422, "amount는 음수일 수 없습니다.")
    c = CashBalance(**body.model_dump())
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@router.get("", response_model=list[CashOut])
async def list_cash(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(CashBalance))).scalars().all()


@router.put("/{cash_id}", response_model=CashOut)
async def update_cash(cash_id: int, body: CashUpdate, db: AsyncSession = Depends(get_db)):
    c = await db.get(CashBalance, cash_id)
    if c is None:
        raise HTTPException(404, "cash not found")
    data = body.model_dump(exclude_unset=True)
    if "amount" in data and data["amount"] is not None and data["amount"] < 0:
        raise HTTPException(422, "amount는 음수일 수 없습니다.")
    for k, v in data.items():
        setattr(c, k, v)
    await db.commit()
    await db.refresh(c)
    return c


@router.delete("/{cash_id}")
async def delete_cash(cash_id: int, db: AsyncSession = Depends(get_db)):
    c = await db.get(CashBalance, cash_id)
    if c is None:
        raise HTTPException(404, "cash not found")
    await db.delete(c)
    await db.commit()
    return {"deleted": cash_id}
