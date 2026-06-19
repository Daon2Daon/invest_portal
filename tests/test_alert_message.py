from types import SimpleNamespace
from app.services.alert.message import build_message


def _asset(currency="USD"):
    return SimpleNamespace(name="Tesla", ticker="TSLA", market="US", currency=currency)


def test_message_absolute_usd():
    alert = SimpleNamespace(basis="ABSOLUTE", direction="ABOVE", value=250.0)
    msg = build_message(_asset("USD"), alert, current_price=251.0, target_price=250.0)
    assert "TSLA" in msg
    assert "$251.00" in msg
    assert "$250.00" in msg
    assert "≥" in msg


def test_message_purchase_avg_krw():
    asset = SimpleNamespace(name="삼성전자", ticker="005930", market="KR", currency="KRW")
    alert = SimpleNamespace(basis="PURCHASE_AVG", direction="BELOW", value=15.0)
    msg = build_message(asset, alert, current_price=59500.0, target_price=59500.0)
    assert "평균매입가 대비" in msg
    assert "-15%" in msg
    assert "59,500원" in msg
    assert "≤" in msg
