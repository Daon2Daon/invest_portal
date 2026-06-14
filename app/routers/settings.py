from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.services.settings.settings_manager import get_setting, set_setting

router = APIRouter(prefix="/api/settings", tags=["settings"])

_CAT = "notification"


class SettingIn(BaseModel):
    category: str
    key: str
    value: str
    is_secret: bool = False


class TelegramIn(BaseModel):
    bot_token: str | None = None   # 빈/None이면 기존 토큰 유지
    chat_id: str | None = None


@router.get("/telegram")
async def get_telegram(db: AsyncSession = Depends(get_db)):
    token = await get_setting(db, _CAT, "telegram_bot_token")
    chat_id = await get_setting(db, _CAT, "telegram_chat_id")
    return {"bot_token_set": bool(token), "chat_id": chat_id or ""}


@router.put("/telegram")
async def put_telegram(body: TelegramIn, db: AsyncSession = Depends(get_db)):
    if body.bot_token:
        await set_setting(db, _CAT, "telegram_bot_token", body.bot_token, is_secret=True)
    if body.chat_id is not None:
        await set_setting(db, _CAT, "telegram_chat_id", body.chat_id, is_secret=False)
    return {"status": "ok"}


@router.get("/{category}/{key}")
async def read(category: str, key: str, db: AsyncSession = Depends(get_db)):
    return {"value": await get_setting(db, category, key)}


@router.put("")
async def write(body: SettingIn, db: AsyncSession = Depends(get_db)):
    await set_setting(db, body.category, body.key, body.value, body.is_secret)
    return {"status": "ok"}
