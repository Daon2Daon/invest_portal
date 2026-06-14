from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Holding, Asset
from app.schemas.holding import HoldingCreate, HoldingWithAssetCreate, HoldingUpdate, HoldingOut
from app.services.market.asset_class import default_asset_class

router = APIRouter(prefix="/api/holdings", tags=["holdings"])


@router.post("", response_model=HoldingOut)
async def create_holding(body: HoldingCreate, db: AsyncSession = Depends(get_db)):
    """기존 자산(asset_id)에 보유 lot 추가(분할매수)."""
    h = Holding(**body.model_dump())
    db.add(h)
    await db.commit()
    await db.refresh(h)
    return h


@router.post("/with-asset", response_model=HoldingOut)
async def create_with_asset(body: HoldingWithAssetCreate, db: AsyncSession = Depends(get_db)):
    """자산 upsert((ticker, market) 기준) + 보유 생성을 한 번에 처리."""
    asset = (await db.execute(
        select(Asset).where(Asset.ticker == body.ticker, Asset.market == body.market)
    )).scalar_one_or_none()
    if asset is None:
        asset = Asset(
            ticker=body.ticker, name=body.name, asset_type=body.asset_type, market=body.market,
            currency=body.currency, data_source=body.data_source, fetch_symbol=body.fetch_symbol,
            name_en=body.name_en,
            asset_class=body.asset_class or default_asset_class(body.asset_type),
        )
        db.add(asset)
        await db.flush()   # asset_id 확보(커밋 전)
    h = Holding(
        asset_id=asset.asset_id, quantity=body.quantity, purchase_price=body.purchase_price,
        purchase_date=body.purchase_date, fee=body.fee, memo=body.memo,
    )
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
