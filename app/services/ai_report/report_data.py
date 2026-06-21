"""포트폴리오·추세·종목수익률 → LLM 입력용 마크다운 블록. 수집 + 순수 변환."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset
from app.services.portfolio.portfolio_service import get_portfolio
from app.services.market.history_service import get_history
from app.services.snapshot import snapshot_store

_KST = ZoneInfo("Asia/Seoul")
_TREND_DAYS = 30      # 추세 표에 포함할 스냅샷 범위(일)
_HISTORY_DAYS = 45    # 종목 수익률 산정용 일봉 조회 범위(거래일 ~20 확보)
_W1, _M1 = 5, 20      # 최근 1주/1달 거래일 수


def pct_change(closes: list[float], periods: int) -> float | None:
    """종가 리스트에서 마지막 대비 periods 거래일 전 변동률(%). 부족하면 None."""
    if len(closes) <= periods:
        return None
    prev = closes[-1 - periods]
    if not prev:
        return None
    return (closes[-1] / prev - 1) * 100


def _fmt(n: float) -> str:
    return f"{n:,.0f}"


def _ret(v: float | None) -> str:
    return f"{v:+.1f}%" if v is not None else "(이력 없음)"


def build_input_block(portfolio: dict, trend: list[dict],
                      returns: dict[int, dict | None], today: str) -> str:
    """수집된 데이터 → 마크다운 입력 블록(순수)."""
    s = portfolio["summary"]
    lines: list[str] = []
    lines.append(f"## 포트폴리오 종합 데이터 ({today} 기준, 통화 KRW)\n")

    lines.append("### 요약")
    lines.append(f"- 총자산: {_fmt(s['total_value_krw'])}")
    lines.append(f"- 투자원금: {_fmt(s['total_cost_krw'])}")
    lines.append(f"- 평가손익: {s['total_profit_loss_krw']:+,.0f} ({s['total_profit_loss_pct']:+.1f}%)")
    lines.append(f"- 현금성: {_fmt(s['total_cash_krw'])}\n")

    lines.append("### 자산군별 비중")
    lines.append("| 자산군 | 평가액 | 비중 |")
    lines.append("|---|---|---|")
    for a in portfolio["allocation"]:
        lines.append(f"| {a['asset_class']} | {_fmt(a['value_krw'])} | {a['weight_pct']:.1f}% |")
    lines.append("")

    lines.append("### 보유 종목")
    lines.append("| 종목 | 자산군 | 평가액 | 비중 | 손익 | 최근1주 | 최근1달 |")
    lines.append("|---|---|---|---|---|---|---|")
    for p in portfolio["positions"]:
        r = returns.get(p["asset_id"]) or {}
        w1 = _ret(r.get("w1")) if r else "(이력 없음)"
        m1 = _ret(r.get("m1")) if r else "(이력 없음)"
        lines.append(
            f"| {p['name']}({p['ticker']}) | {p['asset_class']} | {_fmt(p['value_krw'])} | "
            f"{p['weight_pct']:.1f}% | {p['profit_loss_pct']:+.1f}% | {w1} | {m1} |"
        )
    lines.append("")

    lines.append("### 최근 자산 추세 (일별 스냅샷)")
    if trend:
        lines.append("| 날짜 | 총자산 | 평가손익 |")
        lines.append("|---|---|---|")
        for t in trend:
            lines.append(f"| {t['date']} | {_fmt(t['total_value_krw'])} | {t['total_pl_krw']:+,.0f} |")
    else:
        lines.append("(누적된 스냅샷이 없어 추세를 제공할 수 없습니다.)")
    lines.append("")
    return "\n".join(lines)


async def _position_returns(db: AsyncSession, positions: list[dict]) -> dict[int, dict | None]:
    """종목별 최근 1주/1달 수익률. 실패·무이력은 None(폴백)."""
    out: dict[int, dict | None] = {}
    for p in positions:
        asset = await db.get(Asset, p["asset_id"])
        if asset is None:
            out[p["asset_id"]] = None
            continue
        try:
            df = await get_history(asset, _HISTORY_DAYS)
        except Exception:
            df = None
        if df is None or "Close" not in getattr(df, "columns", []):
            out[p["asset_id"]] = None
            continue
        closes = [float(x) for x in df["Close"].tolist()]
        w1 = pct_change(closes, _W1)
        m1 = pct_change(closes, _M1)
        out[p["asset_id"]] = None if (w1 is None and m1 is None) else {"w1": w1, "m1": m1}
    return out


async def collect_input_block(db: AsyncSession) -> str:
    """포트폴리오·추세·종목수익률을 모아 마크다운 입력 블록을 만든다."""
    portfolio = await get_portfolio(db)
    today = datetime.now(_KST).date()
    since = today - timedelta(days=_TREND_DAYS)
    snaps = await snapshot_store.list_snapshots(db, since)
    trend = [
        {"date": r.date.isoformat(),
         "total_value_krw": float(r.total_value_krw),
         "total_pl_krw": float(r.total_pl_krw)}
        for r in snaps
    ]
    returns = await _position_returns(db, portfolio["positions"])
    return build_input_block(portfolio, trend, returns, today.isoformat())
