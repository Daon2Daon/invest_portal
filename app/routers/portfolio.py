from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.schemas.portfolio import PortfolioOut
from app.services.portfolio.portfolio_service import get_portfolio
from app.services.fx.fx_service import refresh_rates

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioOut)
async def portfolio(db: AsyncSession = Depends(get_db)):
    return await get_portfolio(db)


@router.post("/refresh", response_model=PortfolioOut)
async def refresh(db: AsyncSession = Depends(get_db)):
    await refresh_rates(db)        # 환율 갱신 후 재집계 (시세는 get_portfolio가 실시간 조회)
    return await get_portfolio(db)
