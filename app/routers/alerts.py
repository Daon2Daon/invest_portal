from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Asset
from app.schemas.alert import AlertCreate, AlertUpdate, AlertOut
from app.services.alert import alert_store
from app.services.alert.alert_store import list_alerts_view, list_all_alerts_view

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.post("", response_model=AlertOut)
async def create(body: AlertCreate, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, body.asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    if body.basis == "PURCHASE_AVG" and not await alert_store.has_holdings(db, body.asset_id):
        raise HTTPException(422, "보유 종목에만 평균매입가 기준 알림을 설정할 수 있습니다.")
    if body.basis in ("WEEK52_HIGH", "WEEK52_LOW") and asset.data_source == "manual":
        raise HTTPException(422, "수동(manual) 자산은 52주 기준 알림을 설정할 수 없습니다.")
    direction = "BOTH" if body.basis == "REFERENCE" else body.direction
    return await alert_store.create_alert(
        db, body.asset_id, body.basis, direction, body.value, body.note)


@router.get("")
async def list_alerts(asset_id: int | None = None, db: AsyncSession = Depends(get_db)):
    if asset_id is None:
        return await list_all_alerts_view(db)
    return await list_alerts_view(db, asset_id)


@router.put("/{alert_id}", response_model=AlertOut)
async def update(alert_id: int, body: AlertUpdate, db: AsyncSession = Depends(get_db)):
    alert = await alert_store.get_alert(db, alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    data = body.model_dump(exclude_unset=True)
    return await alert_store.update_alert(
        db, alert,
        value=data.get("value"),
        direction=data.get("direction"),
        note=(data["note"] if "note" in data else alert_store._UNSET),
        enabled=data.get("enabled"),
    )


@router.post("/{alert_id}/rearm", response_model=AlertOut)
async def rearm(alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await alert_store.get_alert(db, alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    return await alert_store.rearm_alert(db, alert)


@router.delete("/{alert_id}")
async def delete(alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await alert_store.get_alert(db, alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    await alert_store.delete_alert(db, alert)
    return {"deleted": alert_id}
