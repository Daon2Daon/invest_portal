from app.services.market_summary.message import build_message


def _stats(current, d, w, m, drop):
    return {"current": current, "daily_pct": d, "weekly_pct": w,
            "monthly_pct": m, "wk52_high": current * 1.2, "wk52_drop_pct": drop}


def test_message_kr_holdings_and_index():
    indices = [{"name": "KOSPI", "price": 2800.12, "change_pct": 1.23}]
    holdings = [("삼성전자", "005930", _stats(59500.0, 1.0, -2.0, 3.0, -8.5))]
    msg = build_message("KR", indices, holdings, [])
    assert "한국 증시 마감 요약" in msg
    assert "KOSPI" in msg and "2,800" in msg
    assert "삼성전자" in msg and "59,500원" in msg
    assert "▲" in msg or "▼" in msg  # 종목 등락 표식(이모지 대체)
    assert "📈" not in msg and "📉" not in msg  # 중복 화살표 이모지 제거
    assert "52주 고점 대비" in msg


def test_message_us_watchlist_dollar_and_none_pct():
    indices = [{"name": "S&P 500", "price": 5000.0, "change_pct": None}]
    watch = [("Tesla", "TSLA", _stats(250.0, None, 1.0, 2.0, -5.0))]
    msg = build_message("US", indices, [], watch)
    assert "$250.00" in msg
    assert "관심 종목" in msg
    assert "—" in msg  # daily_pct None → —
