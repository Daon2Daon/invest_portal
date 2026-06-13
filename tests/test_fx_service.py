import pytest
from datetime import date
from unittest.mock import patch
import pandas as pd
from sqlalchemy import select
from app.services.fx.fx_service import refresh_rates, get_rate_to_krw
from app.models import ExchangeRate


@pytest.mark.asyncio
@patch("app.services.fx.fx_service._yf_rate")
async def test_refresh_rates_upserts(mock_rate, db_session):
    mock_rate.side_effect = lambda pair: {"USDKRW=X": 1350.0, "JPYKRW=X": 9.0}[pair]
    await refresh_rates(db_session)
    rows = (await db_session.execute(select(ExchangeRate))).scalars().all()
    pairs = {(r.base_currency, r.quote_currency): float(r.rate) for r in rows}
    assert pairs[("USD", "KRW")] == 1350.0
    assert pairs[("JPY", "KRW")] == 9.0


@pytest.mark.asyncio
@patch("app.services.fx.fx_service._yf_rate")
async def test_refresh_is_idempotent_same_day(mock_rate, db_session):
    mock_rate.side_effect = lambda pair: {"USDKRW=X": 1350.0, "JPYKRW=X": 9.0}[pair]
    await refresh_rates(db_session)
    mock_rate.side_effect = lambda pair: {"USDKRW=X": 1400.0, "JPYKRW=X": 9.5}[pair]
    await refresh_rates(db_session)  # 같은 날짜 → update
    rows = (await db_session.execute(select(ExchangeRate))).scalars().all()
    assert len(rows) == 2
    pairs = {(r.base_currency, r.quote_currency): float(r.rate) for r in rows}
    assert pairs[("USD", "KRW")] == 1400.0


@pytest.mark.asyncio
async def test_get_rate_to_krw_for_krw_is_one(db_session):
    assert await get_rate_to_krw(db_session, "KRW") == 1.0
