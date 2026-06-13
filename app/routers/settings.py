from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.services.settings.settings_manager import get_setting, set_setting

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingIn(BaseModel):
    category: str
    key: str
    value: str
    is_secret: bool = False


@router.get("/{category}/{key}")
async def read(category: str, key: str, db: AsyncSession = Depends(get_db)):
    return {"value": await get_setting(db, category, key)}


@router.put("")
async def write(body: SettingIn, db: AsyncSession = Depends(get_db)):
    await set_setting(db, body.category, body.key, body.value, body.is_secret)
    return {"status": "ok"}
