"""증시 요약 텔레그램 HTML 메시지 빌더(순수). 통화: KR=원(정수), US=$(소수2)."""

_TITLE = {"US": "미국 증시", "KR": "한국 증시"}


def _fmt(price: float, market: str) -> str:
    if market == "KR":
        return f"{price:,.0f}원"
    return f"${price:,.2f}"


def _sign(pct) -> str:
    """부호가 방향을 전달하므로 화살표 이모지 없이 +/- 퍼센트만 출력."""
    if pct is None:
        return "—"
    return f"{pct:+.2f}%"


def _status(pct) -> str:
    """종목당 1회만 붙이는 가벼운 등락 표식(일간 기준)."""
    if pct is None:
        return "·"
    return "▲" if pct >= 0 else "▼"


def build_message(market: str, indices: list[dict],
                  holdings_stats: list[tuple], watchlist_stats: list[tuple]) -> str:
    """holdings_stats/watchlist_stats: [(name, ticker, stats_dict), ...]."""
    lines = [f"<b>📊 {_TITLE.get(market, market)} 마감 요약</b>", "", "[ 주요 지수 ]"]
    for ix in indices:
        lines.append(f"{ix['name']}: {ix['price']:,.2f} ({_sign(ix['change_pct'])})")
    for title, rows in (("보유 종목", holdings_stats), ("관심 종목", watchlist_stats)):
        if not rows:
            continue
        lines.append("")
        lines.append(f"[ {title} ]")
        for name, ticker, s in rows:
            lines.append(f"{_status(s['daily_pct'])} <b>{name}</b> ({ticker})")
            lines.append(f"  {_fmt(s['current'], market)} · "
                         f"일 {_sign(s['daily_pct'])} · 주 {_sign(s['weekly_pct'])} · 월 {_sign(s['monthly_pct'])}")
            lines.append(f"  52주 고점 대비 {s['wk52_drop_pct']:+.1f}%")
    return "\n".join(lines)
