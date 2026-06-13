from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models import AppSetting

_fernet = Fernet(settings.FERNET_KEY.encode())


async def get_setting(db: AsyncSession, category: str, key: str) -> str | None:
    row = (await db.execute(
        select(AppSetting).where(AppSetting.category == category, AppSetting.key == key)
    )).scalar_one_or_none()
    if row is None:
        return None
    if row.is_secret and row.value_enc is not None:
        return _fernet.decrypt(row.value_enc).decode()
    return row.value


async def set_setting(db: AsyncSession, category: str, key: str, value: str,
                      is_secret: bool = False, value_type: str = "string") -> None:
    row = (await db.execute(
        select(AppSetting).where(AppSetting.category == category, AppSetting.key == key)
    )).scalar_one_or_none()
    enc = _fernet.encrypt(value.encode()) if is_secret else None
    plain = None if is_secret else value
    if row is None:
        db.add(AppSetting(category=category, key=key, value=plain, value_enc=enc,
                          is_secret=is_secret, value_type=value_type))
    else:
        row.value, row.value_enc, row.is_secret, row.value_type = plain, enc, is_secret, value_type
    await db.commit()
