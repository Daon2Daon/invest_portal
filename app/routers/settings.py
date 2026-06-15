from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.services.settings.settings_manager import get_setting, set_setting
from app.services.ai import llm_client

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


class AiIn(BaseModel):
    base_url: str | None = None
    api_key: str | None = None      # 빈/None이면 기존 키 유지
    model: str | None = None
    prompt: str | None = None
    enabled: bool | None = None


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


_AI = "ai_gateway"


@router.get("/ai")
async def get_ai(db: AsyncSession = Depends(get_db)):
    return {
        "base_url": await get_setting(db, _AI, "base_url") or "",
        "api_key_set": bool(await get_setting(db, _AI, "api_key")),
        "model": await get_setting(db, _AI, "model") or "",
        "prompt": await get_setting(db, _AI, "prompt") or "",
        "enabled": (await get_setting(db, _AI, "enabled") or "false").lower() == "true",
    }


@router.get("/ai/models")
async def get_ai_models(db: AsyncSession = Depends(get_db)):
    base_url = await get_setting(db, _AI, "base_url")
    api_key = await get_setting(db, _AI, "api_key")
    if not base_url:
        return {"models": [], "error": "base_url이 설정되지 않았습니다."}
    try:
        return {"models": await llm_client.list_models(base_url, api_key or "")}
    except llm_client.LiteLLMError as e:
        return {"models": [], "error": str(e)}


@router.put("/ai")
async def put_ai(body: AiIn, db: AsyncSession = Depends(get_db)):
    if body.base_url is not None:
        await set_setting(db, _AI, "base_url", body.base_url, is_secret=False)
    if body.api_key:
        await set_setting(db, _AI, "api_key", body.api_key, is_secret=True)
    if body.model is not None:
        await set_setting(db, _AI, "model", body.model, is_secret=False)
    if body.prompt is not None:
        await set_setting(db, _AI, "prompt", body.prompt, is_secret=False)
    if body.enabled is not None:
        await set_setting(db, _AI, "enabled", "true" if body.enabled else "false", is_secret=False)
    return {"status": "ok"}


@router.get("/{category}/{key}")
async def read(category: str, key: str, db: AsyncSession = Depends(get_db)):
    return {"value": await get_setting(db, category, key)}


@router.put("")
async def write(body: SettingIn, db: AsyncSession = Depends(get_db)):
    await set_setting(db, body.category, body.key, body.value, body.is_secret)
    return {"status": "ok"}
