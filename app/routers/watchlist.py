from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.portfolio.watchlist_service import get_watchlist

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("")
async def watchlist(db: AsyncSession = Depends(get_db)):
    return await get_watchlist(db)
