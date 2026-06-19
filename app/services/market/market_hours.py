"""시장 개장(거래일+장중) 판정. now는 tz-aware datetime을 인자로 받아 순수·결정적이다.
점심 휴장(예: JPX)은 단순화해 무시한다(개인용 알림 영향 경미)."""
from datetime import datetime, timezone, timedelta

_CAL_NAMES = {"US": "NYSE", "KR": "XKRX", "JP": "JPX"}
_cal_cache: dict = {}


def _calendar(name: str):
    if name not in _cal_cache:
        import pandas_market_calendars as mcal
        _cal_cache[name] = mcal.get_calendar(name)
    return _cal_cache[name]


def is_market_open(market: str, now: datetime) -> bool:
    if market == "CRYPTO":
        return True
    name = _CAL_NAMES.get(market)
    if name is None:
        return True  # 미지 시장 → fail-open(알림 누락 방지)
    try:
        cal = _calendar(name)
        now_utc = now.astimezone(timezone.utc)
        start = (now_utc - timedelta(days=1)).date().isoformat()
        end = (now_utc + timedelta(days=1)).date().isoformat()
        sched = cal.schedule(start_date=start, end_date=end)
        for _, row in sched.iterrows():
            if row["market_open"] <= now_utc <= row["market_close"]:
                return True
        return False
    except Exception:
        return True  # 라이브러리 오류 → fail-open
