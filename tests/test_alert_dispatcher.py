import pytest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock, MagicMock

from app.services.market.types import Quote
import app.services.alert.alert_dispatcher as disp


class _FakeSession:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def commit(self): pass
    async def rollback(self): pass


def _asset(asset_id=1, market="US"):
    return SimpleNamespace(asset_id=asset_id, market=market, name="N", ticker="T", currency="USD")


def _alert(alert_id=1, basis="ABSOLUTE", direction="ABOVE", value=100.0):
    return SimpleNamespace(alert_id=alert_id, basis=basis, direction=direction, value=value,
                           enabled=True, is_triggered=False, triggered_at=None, last_notified_at=None)


def _patches(pairs, quote, market_open=True, send_ok=True, basis_price=None):
    return [
        patch.object(disp, "SessionLocal", return_value=_FakeSession()),
        patch.object(disp.alert_store, "list_active_with_assets", AsyncMock(return_value=pairs)),
        patch.object(disp, "is_market_open", return_value=market_open),
        patch.object(disp, "get_quote", AsyncMock(return_value=quote)),
        patch.object(disp, "resolve_basis_price", AsyncMock(return_value=basis_price)),
        patch.object(disp.telegram_service, "send_message", AsyncMock(return_value=send_ok)),
        patch.object(disp.asyncio, "sleep", AsyncMock()),
    ]


async def _run(ctxs):
    started = [c.__enter__() for c in ctxs]
    try:
        await disp.evaluate_tick()
    finally:
        for c in ctxs:
            c.__exit__(None, None, None)
    return started


@pytest.mark.asyncio
async def test_fires_and_updates_state():
    asset, alert = _asset(), _alert(value=100.0)
    q = Quote(price=150.0, currency="USD", status="ok")
    ctxs = _patches([(alert, asset)], q)
    await _run(ctxs)
    assert alert.is_triggered is True
    assert alert.enabled is False
    assert alert.triggered_at is not None


@pytest.mark.asyncio
async def test_skips_when_market_closed():
    asset, alert = _asset(), _alert()
    q = Quote(price=150.0, currency="USD", status="ok")
    send = AsyncMock(return_value=True)
    with patch.object(disp, "SessionLocal", return_value=_FakeSession()), \
         patch.object(disp.alert_store, "list_active_with_assets", AsyncMock(return_value=[(alert, asset)])), \
         patch.object(disp, "is_market_open", return_value=False), \
         patch.object(disp, "get_quote", AsyncMock(return_value=q)) as gq, \
         patch.object(disp.telegram_service, "send_message", send):
        await disp.evaluate_tick()
    gq.assert_not_awaited()
    send.assert_not_awaited()
    assert alert.is_triggered is False


@pytest.mark.asyncio
async def test_skips_when_quote_error():
    asset, alert = _asset(), _alert()
    q = Quote(price=0.0, currency="USD", status="error")
    send = AsyncMock(return_value=True)
    with patch.object(disp, "SessionLocal", return_value=_FakeSession()), \
         patch.object(disp.alert_store, "list_active_with_assets", AsyncMock(return_value=[(alert, asset)])), \
         patch.object(disp, "is_market_open", return_value=True), \
         patch.object(disp, "get_quote", AsyncMock(return_value=q)), \
         patch.object(disp.telegram_service, "send_message", send):
        await disp.evaluate_tick()
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_quote_fetched_once_per_asset():
    asset = _asset()
    a1, a2 = _alert(alert_id=1, value=100.0), _alert(alert_id=2, value=120.0)
    q = Quote(price=150.0, currency="USD", status="ok")
    with patch.object(disp, "SessionLocal", return_value=_FakeSession()), \
         patch.object(disp.alert_store, "list_active_with_assets", AsyncMock(return_value=[(a1, asset), (a2, asset)])), \
         patch.object(disp, "is_market_open", return_value=True), \
         patch.object(disp, "get_quote", AsyncMock(return_value=q)) as gq, \
         patch.object(disp, "resolve_basis_price", AsyncMock(return_value=None)), \
         patch.object(disp.telegram_service, "send_message", AsyncMock(return_value=True)), \
         patch.object(disp.asyncio, "sleep", AsyncMock()):
        await disp.evaluate_tick()
    assert gq.await_count == 1


@pytest.mark.asyncio
async def test_scheduler_registers_alert_tick():
    from app.services.scheduler import scheduler as sched_mod
    # 깨끗한 상태에서 시작
    sched_mod.shutdown_scheduler()
    sched_mod.start_scheduler()
    try:
        s = sched_mod._scheduler
        ids = {job.id for job in s.get_jobs()}
        assert "dispatch_tick" in ids
        assert "alert_tick" in ids
    finally:
        sched_mod.shutdown_scheduler()
