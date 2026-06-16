import pytest
from datetime import datetime, date
from zoneinfo import ZoneInfo
from unittest.mock import patch, AsyncMock, MagicMock

from app.models import Schedule
from app.services.scheduler import dispatcher as d

_KST = ZoneInfo("Asia/Seoul")


def _sched(**kw):
    base = dict(feature_type="chart_analysis", target_id=1, send_time="08:00",
                days_of_week="0,1,2,3,4,5,6", enabled=True, last_run_date=None)
    base.update(kw)
    return Schedule(**base)


def test_is_due_true_when_time_passed_and_not_run():
    now = datetime(2026, 6, 16, 9, 0, tzinfo=_KST)  # 화요일(weekday=1), 08:00 지남
    assert d._is_due(_sched(), now) is True


def test_is_due_false_before_time():
    now = datetime(2026, 6, 16, 7, 30, tzinfo=_KST)
    assert d._is_due(_sched(), now) is False


def test_is_due_false_wrong_weekday():
    now = datetime(2026, 6, 16, 9, 0, tzinfo=_KST)  # 화(1)
    assert d._is_due(_sched(days_of_week="5,6"), now) is False


def test_is_due_false_already_ran_today():
    now = datetime(2026, 6, 16, 9, 0, tzinfo=_KST)
    assert d._is_due(_sched(last_run_date=date(2026, 6, 16)), now) is False


def test_is_due_false_when_disabled():
    now = datetime(2026, 6, 16, 9, 0, tzinfo=_KST)
    assert d._is_due(_sched(enabled=False), now) is False


@pytest.mark.asyncio
async def test_dispatch_tick_runs_due_and_sets_last_run():
    sched = _sched(send_time="00:00")   # 항상 시각 통과
    handler = AsyncMock()
    db = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=False)
    with patch.object(d, "SessionLocal", return_value=cm), \
         patch.object(d.schedule_store, "list_enabled", AsyncMock(return_value=[sched])), \
         patch.dict(d.HANDLERS, {"chart_analysis": handler}, clear=True):
        await d.dispatch_tick()
    handler.assert_awaited_once()
    assert sched.last_run_date is not None
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_dispatch_tick_failure_does_not_set_last_run():
    sched = _sched(send_time="00:00")
    handler = AsyncMock(side_effect=RuntimeError("boom"))
    db = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=False)
    with patch.object(d, "SessionLocal", return_value=cm), \
         patch.object(d.schedule_store, "list_enabled", AsyncMock(return_value=[sched])), \
         patch.dict(d.HANDLERS, {"chart_analysis": handler}, clear=True):
        await d.dispatch_tick()   # 예외가 tick 밖으로 새지 않아야 함
    assert sched.last_run_date is None
    db.rollback.assert_awaited()
