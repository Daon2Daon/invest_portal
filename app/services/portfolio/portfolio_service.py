def aggregate_position(lots: list[dict], current_price: float, fx_now: float) -> dict:
    """동일 자산의 lot들을 자산 통화 기준으로 집계하고 현재 환율(fx_now)로 KRW 환산한다.

    매수시점 환율은 쓰지 않는다(해외 자산 과거가치 산정 불필요).
    cost_native  = Σ (quantity * purchase_price) + fee
    value_native = Σ quantity * current_price
    *_krw        = *_native * fx_now
    """
    total_qty = sum(l["quantity"] for l in lots)
    cost_native = sum(l["quantity"] * l["purchase_price"] + (l.get("fee") or 0) for l in lots)
    value_native = total_qty * current_price
    avg_price = (sum(l["quantity"] * l["purchase_price"] for l in lots) / total_qty) if total_qty else 0
    pl_native = value_native - cost_native
    pl_pct = (pl_native / cost_native * 100) if cost_native else 0
    return {
        "quantity": total_qty,
        "avg_price": avg_price,
        "cost_native": cost_native,
        "value_native": value_native,
        "profit_loss_native": pl_native,
        "cost_krw": cost_native * fx_now,
        "value_krw": value_native * fx_now,
        "profit_loss_krw": pl_native * fx_now,
        "profit_loss_pct": pl_pct,
    }


def build_allocation(positions: list[dict], total_cash: float, total_value: float) -> list[dict]:
    """자산군별 평가액·비중을 집계한다. 현금은 '현금성' 자산군으로 더한다.
    asset_class가 None/빈값이면 '기타'로 묶는다."""
    sums: dict[str, float] = {}
    for p in positions:
        key = p.get("asset_class") or "기타"
        sums[key] = sums.get(key, 0.0) + p["value_krw"]
    if total_cash:
        sums["현금성"] = sums.get("현금성", 0.0) + total_cash
    out = [{"asset_class": k, "value_krw": v,
            "weight_pct": (v / total_value * 100) if total_value else 0} for k, v in sums.items()]
    out.sort(key=lambda x: x["value_krw"], reverse=True)
    return out


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Asset, Holding, CashBalance
from app.services.market.quote_service import get_quote
from app.services.fx.fx_service import get_rate_to_krw


async def get_portfolio(db: AsyncSession) -> dict:
    assets = (await db.execute(select(Asset).where(Asset.is_active == True))).scalars().all()  # noqa: E712
    positions = []
    total_value = 0.0
    for asset in assets:
        lots = (await db.execute(
            select(Holding).where(Holding.asset_id == asset.asset_id)
        )).scalars().all()
        if not lots:
            continue
        quote = await get_quote(asset)
        fx_now = await get_rate_to_krw(db, asset.currency) or 0.0
        lot_dicts = [dict(quantity=float(l.quantity), purchase_price=float(l.purchase_price),
                          fee=float(l.fee or 0)) for l in lots]
        agg = aggregate_position(lot_dicts, current_price=quote.price, fx_now=fx_now)
        total_value += agg["value_krw"]
        positions.append({
            "asset_id": asset.asset_id, "ticker": asset.ticker, "name": asset.name,
            "market": asset.market, "currency": asset.currency,
            "asset_class": asset.asset_class or "기타",
            "current_price": quote.price, "price_status": quote.status, **agg,
        })

    # 현금: 통화별 KRW 환산. 매수·매도와 연동하지 않음(독립 관리).
    cash_rows = (await db.execute(select(CashBalance))).scalars().all()
    cash = []
    total_cash = 0.0
    for c in cash_rows:
        fx = await get_rate_to_krw(db, c.currency) or 0.0
        value_krw = float(c.amount) * fx
        total_cash += value_krw
        total_value += value_krw
        cash.append({"id": c.id, "currency": c.currency, "amount": float(c.amount),
                     "label": c.label, "value_krw": value_krw})

    # 비중은 종목+현금 전체(total_value) 기준.
    for p in positions:
        p["weight_pct"] = (p["value_krw"] / total_value * 100) if total_value else 0
    for c in cash:
        c["weight_pct"] = (c["value_krw"] / total_value * 100) if total_value else 0

    total_cost = sum(p["cost_krw"] for p in positions)
    positions_value = total_value - total_cash   # 종목 평가액 합(현금 제외)
    allocation = build_allocation(positions, total_cash, total_value)
    return {
        "positions": positions,
        "cash": cash,
        "allocation": allocation,
        "summary": {
            "total_value_krw": total_value,
            "total_cost_krw": total_cost,
            "total_profit_loss_krw": positions_value - total_cost,
            "total_profit_loss_pct": ((positions_value - total_cost) / total_cost * 100) if total_cost else 0,
            "total_cash_krw": total_cash,
        },
    }
