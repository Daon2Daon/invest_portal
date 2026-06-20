"""가격 알림 텔레그램 메시지(HTML) 빌더. asset/alert는 속성 접근만 한다(ORM 또는 단순객체)."""

_BASIS_LABEL = {
    "ABSOLUTE": "목표가",
    "PURCHASE_AVG": "평균매입가 대비",
    "WEEK52_HIGH": "52주 고점 대비",
    "WEEK52_LOW": "52주 저점 대비",
    "REFERENCE": "변동률 감시",
}


def _fmt(price: float, currency: str) -> str:
    if currency == "KRW":
        return f"{price:,.0f}원"
    sym = {"USD": "$", "JPY": "¥"}.get(currency, "")
    return f"{sym}{price:,.2f}"


def build_message(asset, alert, current_price: float, target_price: float) -> str:
    arrow = "≥" if alert.direction == "ABOVE" else "≤"
    if alert.basis == "ABSOLUTE":
        edge = "이상" if alert.direction == "ABOVE" else "이하"
        cond = f"{_BASIS_LABEL['ABSOLUTE']} {_fmt(float(alert.value), asset.currency)} {edge}"
    else:
        sign = "+" if alert.direction == "ABOVE" else "-"
        cond = f"{_BASIS_LABEL[alert.basis]} {sign}{float(alert.value):g}% 도달"
    return (
        f"🔔 <b>{asset.name}</b> ({asset.ticker}·{asset.market})\n"
        f"조건: {cond}\n"
        f"현재가 {_fmt(current_price, asset.currency)} {arrow} 목표 {_fmt(target_price, asset.currency)}"
    )


def build_reference_message(asset, alert, current_price: float, reference_price: float) -> str:
    change_pct = (current_price - reference_price) / reference_price * 100.0
    direction = "상승" if change_pct >= 0 else "하락"
    return (
        f"🔔 <b>{asset.name}</b> ({asset.ticker}·{asset.market})\n"
        f"조건: {_BASIS_LABEL['REFERENCE']} ±{float(alert.value):g}%\n"
        f"급격한 {direction}! 기준가 {_fmt(reference_price, asset.currency)} → "
        f"현재가 {_fmt(current_price, asset.currency)} ({change_pct:+.2f}%)"
    )
