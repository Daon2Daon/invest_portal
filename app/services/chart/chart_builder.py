"""자산 → 차트 PNG. 라우터/디스패처가 공유(HTTPException 대신 도메인 예외)."""
import asyncio

from app.services.market.history_service import get_history
from app.services.chart.chart_service import generate_ta_chart, to_weekly

_DAYS = {"daily": 730, "weekly": 1825}


class ChartDataError(Exception):
    """차트용 시세 이력이 없거나 부족."""


async def build_png(asset, period: str) -> bytes:
    if period not in _DAYS:
        raise ChartDataError("period는 daily 또는 weekly")
    df = await get_history(asset, _DAYS[period])
    if df is None or len(df) < 20:
        raise ChartDataError("차트용 시세 이력을 가져올 수 없습니다(수동/이력없음 자산이거나 데이터 부족).")
    if period == "weekly":
        df = to_weekly(df)
        if len(df) < 20:
            raise ChartDataError("주봉 데이터가 부족합니다.")
    label = "WEEKLY" if period == "weekly" else "DAILY"
    return await asyncio.to_thread(generate_ta_chart, df, asset.ticker, asset.name, label)
