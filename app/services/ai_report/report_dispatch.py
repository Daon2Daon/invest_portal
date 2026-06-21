"""AI 리포트를 텔레그램으로 발송(마크다운 → HTML, 길이 분할)."""
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIReport
from app.services.ai import telegram_md
from app.services.notification import telegram_service


async def send_report(db: AsyncSession, report: AIReport) -> int:
    """발송한 메시지 조각 수 반환. 텔레그램 미설정 시 TelegramNotConfigured 전파."""
    chunks = telegram_md.split_message(telegram_md.md_to_telegram_html(report.content_md))
    sent = 0
    for i, chunk in enumerate(chunks):
        if i > 0:
            await asyncio.sleep(2)
        if await telegram_service.send_message(db, chunk):
            sent += 1
    return sent
