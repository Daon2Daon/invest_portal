from app.services.risk_signal import message as m


def test_empty_digest():
    out = m.build_digest_message([])
    assert "위험신호가 없습니다" in out


def test_digest_groups_sections():
    signals = [
        {"ticker": "005930", "name": "삼성", "category": "technical",
         "type": "RSI", "direction": "과매수", "detail": "73.2"},
        {"ticker": "005930", "name": "삼성", "category": "technical",
         "type": "MACD", "direction": "데드크로스", "detail": ""},
        {"category": "concentration", "type": "종목 과중", "name": "삼성(005930)", "detail": "62.0%"},
    ]
    out = m.build_digest_message(signals)
    assert "기술적 신호" in out and "비중 편향" in out
    assert "삼성" in out and "RSI" in out and "과매수" in out and "73.2" in out
    assert "데드크로스" in out
    assert "종목 과중" in out and "62.0%" in out
