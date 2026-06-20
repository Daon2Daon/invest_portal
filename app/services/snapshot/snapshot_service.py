"""일별 포트폴리오 스냅샷: get_portfolio 결과를 테이블 행으로 변환·적재한다."""
from datetime import date


def build_snapshot_row(portfolio: dict, today: date) -> dict:
    """get_portfolio() 반환 dict + 날짜 → portfolio_snapshots 컬럼 dict(순수)."""
    s = portfolio["summary"]
    return {
        "date": today,
        "total_value_krw": s["total_value_krw"],
        "total_cost_krw": s["total_cost_krw"],
        "total_pl_krw": s["total_profit_loss_krw"],
        "total_cash_krw": s["total_cash_krw"],
        "allocation": [
            {"asset_class": a["asset_class"], "value_krw": a["value_krw"]}
            for a in portfolio["allocation"]
        ],
    }
