"""위험신호 목록 → 텔레그램 HTML 다이제스트(순수)."""

_HEADER = "<b>⚠️ 위험신호 다이제스트</b>"


def build_digest_message(signals: list[dict]) -> str:
    if not signals:
        return f"{_HEADER}\n\n현재 위험신호가 없습니다."
    tech = [s for s in signals if s["category"] == "technical"]
    conc = [s for s in signals if s["category"] == "concentration"]
    lines = [_HEADER]
    if tech:
        lines += ["", "[ 기술적 신호 ]"]
        for s in tech:
            detail = f" {s['detail']}" if s.get("detail") else ""
            lines.append(f"<b>{s['name']}</b> ({s['ticker']}): {s['type']} {s['direction']}{detail}")
    if conc:
        lines += ["", "[ 비중 편향 ]"]
        for s in conc:
            lines.append(f"{s['type']}: {s['name']} {s['detail']}")
    return "\n".join(lines)
