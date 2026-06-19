"""price_alerts CRUD + 조회. 라우터·디스패처가 공유."""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, Holding, PriceAlert

_UNSET = object()


async def create_alert(db: AsyncSession, asset_id: int, basis: str, direction: str,
                       value: float, note: str | None = None) -> PriceAlert:
    alert = PriceAlert(asset_id=asset_id, basis=basis, direction=direction,
                       value=value, note=note)
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


async def get_alert(db: AsyncSession, alert_id: int) -> PriceAlert | None:
    return await db.get(PriceAlert, alert_id)


async def list_by_asset(db: AsyncSession, asset_id: int) -> list[PriceAlert]:
    return list((await db.execute(
        select(PriceAlert).where(PriceAlert.asset_id == asset_id).order_by(PriceAlert.alert_id)
    )).scalars().all())


async def list_active_with_assets(db: AsyncSession) -> list[tuple[PriceAlert, Asset]]:
    """enabled & not triggered 알림 + 활성 자산 조인. (alert, asset) 튜플 리스트."""
    rows = (await db.execute(
        select(PriceAlert, Asset).join(Asset, Asset.asset_id == PriceAlert.asset_id).where(
            PriceAlert.enabled.is_(True),
            PriceAlert.is_triggered.is_(False),
            Asset.is_active.is_(True),
        )
    )).all()
    return [(r[0], r[1]) for r in rows]


async def has_holdings(db: AsyncSession, asset_id: int) -> bool:
    n = (await db.execute(
        select(func.count()).select_from(Holding).where(Holding.asset_id == asset_id)
    )).scalar_one()
    return n > 0


async def update_alert(db: AsyncSession, alert: PriceAlert, *, value=None, direction=None,
                       note=_UNSET, enabled=None) -> PriceAlert:
    if value is not None:
        alert.value = value
    if direction is not None:
        alert.direction = direction
    if note is not _UNSET:
        alert.note = note
    if enabled is not None:
        alert.enabled = enabled
    await db.commit()
    await db.refresh(alert)
    return alert


async def rearm_alert(db: AsyncSession, alert: PriceAlert) -> PriceAlert:
    alert.enabled = True
    alert.is_triggered = False
    alert.triggered_at = None
    await db.commit()
    await db.refresh(alert)
    return alert


async def delete_alert(db: AsyncSession, alert: PriceAlert) -> None:
    await db.delete(alert)
    await db.commit()
