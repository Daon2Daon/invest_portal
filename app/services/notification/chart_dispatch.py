"""차트 2장 + best-effort AI 분석 텔레그램 발송. 수동 라우트와 스케줄러가 공유."""
import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chart.chart_builder import build_png
from app.services.market.quote_service import get_quote
from app.services.notification import telegram_service
from app.services.ai import chart_analyzer
from app.services.ai import telegram_md
from app.services.ai import analysis_store

_log = logging.getLogger(__name__)


async def send_chart_telegram(db: AsyncSession, asset, trigger: str = "manual") -> dict:
    """일봉/주봉 발송 후 AI 분석을 best-effort로 저장·발송. TelegramNotConfigured·ChartDataError는 전파."""
    quote = await get_quote(asset)
    caption = f"<b>{asset.name}</b> ({asset.ticker}·{asset.market})\n현재가: {quote.price:,} {asset.currency}"
    images: list[tuple[bytes, str]] = []
    sent = 0
    for i, period in enumerate(("daily", "weekly")):
        if i > 0:
            await asyncio.sleep(1)   # 텔레그램 연속 사진 rate limit 회피
        png = await build_png(asset, period)
        images.append((png, "image/png"))
        cap = f"{caption}\n[{period.upper()}]"
        if await telegram_service.send_photo(db, png, cap):
            sent += 1

    analysis_sent = False
    try:
        raw, model = await chart_analyzer.analyze_raw(db, images, asset.ticker, asset.name, asset.market)
        try:
            await analysis_store.create_and_prune(db, asset.asset_id, raw, model, trigger=trigger)
        except Exception as e:   # noqa: BLE001 — 저장 실패가 발송을 막지 않도록
            _log.warning("AI 분석 저장 실패(발송은 진행): %s", e)
        parts = telegram_md.split_message(telegram_md.md_to_telegram_html(raw))
        for i, part in enumerate(parts):
            if i > 0:
                await asyncio.sleep(1)
            await telegram_service.send_message(db, part)
        analysis_sent = bool(parts)
    except (chart_analyzer.AnalysisDisabled, chart_analyzer.AnalysisNotConfigured):
        pass   # AI 미설정/비활성 → 차트만 발송
    except Exception as e:   # noqa: BLE001 — AI 실패가 차트 발송을 막지 않도록 best-effort
        _log.warning("AI 분석 발송 실패(차트는 발송됨): %s", e)

    return {"sent": sent, "ok": sent > 0, "analysis_sent": analysis_sent}
