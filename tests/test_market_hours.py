import datetime as dt
from datetime import timezone
from app.services.market.market_hours import is_market_open


def _utc(y, m, d, hh, mm):
    return dt.datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def test_crypto_always_open():
    assert is_market_open("CRYPTO", _utc(2026, 6, 20, 3, 0)) is True  # 주말이어도


def test_unknown_market_fail_open():
    assert is_market_open("XX", _utc(2026, 6, 17, 3, 0)) is True


def test_nyse_open_during_session():
    # 2026-06-17(수) 15:00 UTC = 11:00 ET → 개장
    assert is_market_open("US", _utc(2026, 6, 17, 15, 0)) is True


def test_nyse_closed_premarket():
    # 2026-06-17 08:00 UTC = 04:00 ET → 폐장
    assert is_market_open("US", _utc(2026, 6, 17, 8, 0)) is False


def test_nyse_closed_weekend():
    # 2026-06-20 토요일
    assert is_market_open("US", _utc(2026, 6, 20, 15, 0)) is False


def test_xkrx_open_during_session():
    # 2026-06-17 01:00 UTC = 10:00 KST → 개장
    assert is_market_open("KR", _utc(2026, 6, 17, 1, 0)) is True


def test_xkrx_closed_after_hours():
    # 2026-06-17 12:00 UTC = 21:00 KST → 폐장
    assert is_market_open("KR", _utc(2026, 6, 17, 12, 0)) is False


def test_jpx_open_during_session():
    # 2026-06-17 01:00 UTC = 10:00 JST → 개장
    assert is_market_open("JP", _utc(2026, 6, 17, 1, 0)) is True


from app.services.market.market_hours import is_trading_day


def test_is_trading_day_weekday_true():
    # 2026-06-17(수) — NYSE/XKRX 모두 거래일
    assert is_trading_day("US", _utc(2026, 6, 17, 15, 0)) is True
    assert is_trading_day("KR", _utc(2026, 6, 17, 1, 0)) is True


def test_is_trading_day_weekend_false():
    # 2026-06-20(토)
    assert is_trading_day("US", _utc(2026, 6, 20, 15, 0)) is False
    assert is_trading_day("KR", _utc(2026, 6, 20, 1, 0)) is False


def test_is_trading_day_crypto_and_unknown_true():
    assert is_trading_day("CRYPTO", _utc(2026, 6, 20, 0, 0)) is True
    assert is_trading_day("XX", _utc(2026, 6, 20, 0, 0)) is True
