import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Asset
from app.schemas.market import ResolveRequest, ResolveResponse, ResolvedAssetOut
from app.schemas.asset import AssetCreate, AssetOut, ManualPriceUpdate
from app.services.market.resolver import AssetResolver
from app.services.market.quote_service import get_quote

router = APIRouter(prefix="/api/assets", tags=["assets"])
_resolver = AssetResolver()


@router.post("/resolve", response_model=ResolveResponse)
async def resolve(req: ResolveRequest):
    result = await asyncio.to_thread(_resolver.resolve, req.ticker, req.market, req.asset_type)
    out = None
    if result.asset is not None:
        out = ResolvedAssetOut(**result.asset.__dict__)
    return ResolveResponse(ok=result.ok, asset=out, tried=result.tried, suggestion=result.suggestion)


@router.post("", response_model=AssetOut)
async def create_asset(body: AssetCreate, db: AsyncSession = Depends(get_db)):
    asset = Asset(**body.model_dump())
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


@router.get("", response_model=list[AssetOut])
async def list_assets(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Asset).where(Asset.is_active == True))).scalars().all()  # noqa: E712


@router.get("/{asset_id}/quote")
async def asset_quote(asset_id: int, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    q = await get_quote(asset)
    return q.__dict__


@router.put("/{asset_id}/manual-price", response_model=AssetOut)
async def update_manual_price(asset_id: int, body: ManualPriceUpdate, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    asset.manual_price = body.manual_price
    asset.manual_price_currency = body.manual_price_currency
    asset.manual_price_updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(asset)
    return asset


@router.delete("/{asset_id}")
async def delete_asset(asset_id: int, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    await db.delete(asset)
    await db.commit()
    return {"deleted": asset_id}
