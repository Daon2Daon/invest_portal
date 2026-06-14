import asyncio
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.settings.settings_manager import get_setting

CATEGORY = "notification"


class TelegramNotConfigured(Exception):
    pass


async def _load_config(db: AsyncSession):
    token = await get_setting(db, CATEGORY, "telegram_bot_token")
    chat_id = await get_setting(db, CATEGORY, "telegram_chat_id")
    return token, chat_id


async def send_photo(db: AsyncSession, png: bytes, caption: str = "") -> bool:
    token, chat_id = await _load_config(db)
    if not token or not chat_id:
        raise TelegramNotConfigured("텔레그램 봇 토큰/chat_id가 설정되지 않았습니다.")
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    files = {"photo": ("chart.png", png, "image/png")}
    data = {"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "HTML"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, data=data, files=files)
    return resp.status_code == 200


async def send_message(db: AsyncSession, text: str) -> bool:
    token, chat_id = await _load_config(db)
    if not token or not chat_id:
        raise TelegramNotConfigured("텔레그램 봇 토큰/chat_id가 설정되지 않았습니다.")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    timeout = httpx.Timeout(60.0, connect=15.0)
    for attempt, backoff in enumerate((1.0, 3.0, 8.0, None)):
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=data)
        if resp.status_code == 200:
            return True
        if resp.status_code == 429 or resp.status_code >= 500:
            if backoff is None:
                return False
            await asyncio.sleep(backoff)
            continue
        return False
    return False
