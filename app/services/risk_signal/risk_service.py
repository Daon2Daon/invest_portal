"""위험신호 설정 로드 + 다이제스트 생성/발송 오케스트레이션."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings.settings_manager import get_setting
from app.services.notification import telegram_service
from app.services.risk_signal import scanner, message

CATEGORY = "risk_signal"

_BOOL_DEFAULTS = {
    "enabled": False,
    "sig_rsi": True, "sig_macd": True, "sig_bollinger": True, "sig_ma": True,
    "sig_concentration_asset": True, "sig_concentration_class": True,
}
_FLOAT_DEFAULTS = {"threshold_asset_pct": 30.0, "threshold_class_pct": 60.0}


async def load_config(db: AsyncSession) -> dict:
    cfg: dict = {}
    for key, default in _BOOL_DEFAULTS.items():
        v = await get_setting(db, CATEGORY, key)
        cfg[key] = default if v is None else v.lower() == "true"
    for key, default in _FLOAT_DEFAULTS.items():
        v = await get_setting(db, CATEGORY, key)
        cfg[key] = default if v in (None, "") else float(v)
    return cfg


async def build_digest(db: AsyncSession) -> str:
    """현재 설정으로 스캔해 다이제스트 텍스트를 만든다(발송 안 함). 미리보기용."""
    cfg = await load_config(db)
    signals = await scanner.scan(db, cfg)
    return message.build_digest_message(signals)


async def build_and_send(db: AsyncSession) -> dict:
    """다이제스트를 만들어 텔레그램 발송. 미설정 시 TelegramNotConfigured 전파."""
    text = await build_digest(db)
    sent = await telegram_service.send_message(db, text)
    return {"sent": bool(sent)}
