def aggregate_position(lots: list[dict], current_price: float, fx_now: float) -> dict:
    """동일 자산의 lot들을 집계해 KRW 기준 손익을 계산한다.

    cost_krw  = Σ quantity * purchase_price * purchase_fx_rate (+fee)
    value_krw = Σ quantity * current_price * fx_now
    """
    total_qty = sum(l["quantity"] for l in lots)
    cost_krw = sum(
        l["quantity"] * l["purchase_price"] * (l["purchase_fx_rate"] or fx_now) + (l.get("fee") or 0)
        for l in lots
    )
    avg_price = (sum(l["quantity"] * l["purchase_price"] for l in lots) / total_qty) if total_qty else 0
    value_krw = total_qty * current_price * fx_now
    pl = value_krw - cost_krw
    pl_pct = (pl / cost_krw * 100) if cost_krw else 0
    return {
        "quantity": total_qty,
        "avg_price": avg_price,
        "cost_krw": cost_krw,
        "value_krw": value_krw,
        "profit_loss_krw": pl,
        "profit_loss_pct": pl_pct,
    }


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Asset, Holding
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
                          purchase_fx_rate=float(l.purchase_fx_rate) if l.purchase_fx_rate else None,
                          fee=float(l.fee or 0)) for l in lots]
        agg = aggregate_position(lot_dicts, current_price=quote.price, fx_now=fx_now)
        total_value += agg["value_krw"]
        positions.append({
            "asset_id": asset.asset_id, "ticker": asset.ticker, "name": asset.name,
            "market": asset.market, "currency": asset.currency,
            "current_price": quote.price, "price_status": quote.status, **agg,
        })
    for p in positions:
        p["weight_pct"] = (p["value_krw"] / total_value * 100) if total_value else 0
    total_cost = sum(p["cost_krw"] for p in positions)
    return {
        "positions": positions,
        "summary": {
            "total_value_krw": total_value,
            "total_cost_krw": total_cost,
            "total_profit_loss_krw": total_value - total_cost,
            "total_profit_loss_pct": ((total_value - total_cost) / total_cost * 100) if total_cost else 0,
        },
    }
