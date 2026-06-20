from datetime import date
import pytest
from app.models import PortfolioSnapshot


@pytest.mark.asyncio
async def test_insert_and_read_snapshot(db_session):
    snap = PortfolioSnapshot(
        date=date(2026, 6, 20),
        total_value_krw=1000, total_cost_krw=800,
        total_pl_krw=200, total_cash_krw=100,
        allocation=[{"asset_class": "주식", "value_krw": 900}],
    )
    db_session.add(snap)
    await db_session.commit()
    assert snap.id is not None
    assert snap.allocation[0]["asset_class"] == "주식"
