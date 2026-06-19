"""5분 tick: 활성 알림을 자산별로 묶어 장중에만 평가하고, 발동 시 텔레그램 1회 발송."""
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.db import SessionLocal
from app.services.alert import alert_store
from app.services.alert.basis import resolve_basis_price
from app.services.alert.evaluator import compute_target, is_fired
from app.services.alert.message import build_message
from app.services.market.market_hours import is_market_open
from app.services.market.quote_service import get_quote
from app.services.notification import telegram_service

_KST = ZoneInfo("Asia/Seoul")
_log = logging.getLogger(__name__)


async def evaluate_tick() -> None:
    now = datetime.now(_KST)
    async with SessionLocal() as db:
        pairs = await alert_store.list_active_with_assets(db)
        # 자산별 그룹: asset_id -> (asset, [alert, ...])
        by_asset: dict[int, tuple] = {}
        for alert, asset in pairs:
            by_asset.setdefault(asset.asset_id, (asset, []))[1].append(alert)

        for asset, alerts in by_asset.values():
            if not is_market_open(asset.market, now):
                continue
            try:
                quote = await get_quote(asset)
            except Exception as e:   # noqa: BLE001
                _log.warning("시세 조회 실패 asset_id=%s: %s", asset.asset_id, e)
                continue
            if quote.status != "ok" or not quote.price:
                continue
            for alert in alerts:
                try:
                    basis_price = await resolve_basis_price(db, asset, alert.basis)
                    if basis_price is None and alert.basis != "ABSOLUTE":
                        continue
                    target = compute_target(alert.basis, alert.direction, float(alert.value), basis_price)
                    if not is_fired(alert.direction, quote.price, target):
                        continue
                    msg = build_message(asset, alert, quote.price, target)
                    try:
                        ok = await telegram_service.send_message(db, msg)
                    except telegram_service.TelegramNotConfigured:
                        _log.info("텔레그램 미설정 — 알림 발송 생략")
                        return
                    if ok:
                        alert.enabled = False
                        alert.is_triggered = True
                        alert.triggered_at = now
                        alert.last_notified_at = now
                        await db.commit()
                    await asyncio.sleep(2)   # 텔레그램 rate-limit 여유
                except Exception as e:   # noqa: BLE001 — 한 건 실패가 나머지를 막지 않게
                    await db.rollback()
                    _log.warning("알림 평가 실패 alert_id=%s: %s", alert.alert_id, e)
