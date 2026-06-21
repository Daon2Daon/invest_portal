"""보유 종목·포트폴리오를 스캔해 위험신호 목록을 만든다(수집+오케스트레이션)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset
from app.services.portfolio.portfolio_service import get_portfolio
from app.services.market.history_service import get_history
from app.services.chart.chart_service import calculate_indicators
from app.services.risk_signal import evaluator

_HISTORY_DAYS = 120   # SMA50 + MACD(26) 계산에 충분한 일봉


async def scan(db: AsyncSession, config: dict) -> list[dict]:
    """기술적(종목별) + 비중(전체) 신호를 모은 리스트. 시세 실패/무이력 종목은 기술 신호 스킵."""
    portfolio = await get_portfolio(db)
    signals: list[dict] = []

    tech_on = any(config.get(k) for k in ("sig_rsi", "sig_macd", "sig_bollinger", "sig_ma"))
    if tech_on:
        for p in portfolio["positions"]:
            asset = await db.get(Asset, p["asset_id"])
            if asset is None:
                continue
            try:
                df = await get_history(asset, _HISTORY_DAYS)
                if df is None or len(df) < 2 or "Close" not in getattr(df, "columns", []):
                    continue
                ind = calculate_indicators(df)
                signals.extend(evaluator.technical_signals(p["ticker"], p["name"], ind, config))
            except Exception:   # noqa: BLE001 — 한 종목 실패(조회·지표계산 포함)가 스캔 전체를 막지 않음
                continue

    signals.extend(evaluator.concentration_signals(portfolio, config))
    return signals
