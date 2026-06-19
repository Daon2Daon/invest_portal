"""종목 통계: 일·주·월 변동률 + 52주 고점/고점대비. history_service 사용."""
from app.services.market.history_service import get_history


async def asset_stats(asset) -> dict | None:
    df = await get_history(asset, 370)
    if df is None or len(df) < 2:
        return None
    close = df["Close"]
    current = float(close.iloc[-1])

    def pct(n: int):
        if len(close) <= n:
            return None
        prev = float(close.iloc[-1 - n])
        return (current - prev) / prev * 100 if prev else None

    wk52_high = float(df["High"].max())
    drop = (current - wk52_high) / wk52_high * 100 if wk52_high else 0.0
    return {
        "current": current,
        "daily_pct": pct(1), "weekly_pct": pct(5), "monthly_pct": pct(21),
        "wk52_high": wk52_high, "wk52_drop_pct": drop,
    }
