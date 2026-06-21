from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.ai_report import report_generator, report_store, report_dispatch
from app.services.ai.llm_client import LiteLLMError
from app.services.notification import telegram_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _serialize(r) -> dict:
    return {"id": r.id, "title": r.title, "content_md": r.content_md,
            "model": r.model, "trigger": r.trigger,
            "created_at": r.created_at.isoformat() if r.created_at else None}


@router.post("")
async def create_report(db: AsyncSession = Depends(get_db)):
    try:
        report = await report_generator.create_report(db, trigger="manual")
    except (report_generator.ReportDisabled, report_generator.ReportNotConfigured) as e:
        raise HTTPException(409, str(e))
    except LiteLLMError as e:
        raise HTTPException(502, str(e))
    return _serialize(report)


@router.get("")
async def list_reports(db: AsyncSession = Depends(get_db)):
    rows = await report_store.list_reports(db)
    return [_serialize(r) for r in rows]


@router.get("/{report_id}")
async def get_report(report_id: int, db: AsyncSession = Depends(get_db)):
    r = await report_store.get_report(db, report_id)
    if r is None:
        raise HTTPException(404, "리포트를 찾을 수 없습니다.")
    return _serialize(r)


@router.delete("/{report_id}")
async def delete_report(report_id: int, db: AsyncSession = Depends(get_db)):
    await report_store.delete_report(db, report_id)
    return {"status": "ok"}


@router.post("/{report_id}/send-telegram")
async def send_telegram(report_id: int, db: AsyncSession = Depends(get_db)):
    r = await report_store.get_report(db, report_id)
    if r is None:
        raise HTTPException(404, "리포트를 찾을 수 없습니다.")
    try:
        sent = await report_dispatch.send_report(db, r)
    except telegram_service.TelegramNotConfigured as e:
        raise HTTPException(409, str(e))
    return {"sent": sent}
