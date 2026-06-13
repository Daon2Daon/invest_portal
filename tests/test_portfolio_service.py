from app.services.portfolio.portfolio_service import aggregate_position


def test_aggregate_position_single_lot_krw():
    lots = [dict(quantity=10, purchase_price=70000, purchase_fx_rate=1, fee=0)]
    pos = aggregate_position(lots, current_price=71000, fx_now=1.0)
    assert pos["quantity"] == 10
    assert pos["avg_price"] == 70000
    assert pos["cost_krw"] == 700000
    assert pos["value_krw"] == 710000
    assert pos["profit_loss_krw"] == 10000
    assert round(pos["profit_loss_pct"], 4) == round(10000 / 700000 * 100, 4)


def test_aggregate_position_usd_with_fx_separates_currency_gain():
    # 매입: 10주 @ $100, 매입환율 1300 → 원가 1,300,000
    # 현재: $110, 현재환율 1350 → 가치 10*110*1350 = 1,485,000
    lots = [dict(quantity=10, purchase_price=100, purchase_fx_rate=1300, fee=0)]
    pos = aggregate_position(lots, current_price=110, fx_now=1350.0)
    assert pos["cost_krw"] == 1300000
    assert pos["value_krw"] == 1485000
    assert pos["profit_loss_krw"] == 185000


def test_aggregate_position_multi_lot_weighted_avg():
    lots = [
        dict(quantity=10, purchase_price=100, purchase_fx_rate=1, fee=0),
        dict(quantity=30, purchase_price=200, purchase_fx_rate=1, fee=0),
    ]
    pos = aggregate_position(lots, current_price=200, fx_now=1.0)
    assert pos["quantity"] == 40
    assert pos["avg_price"] == (10 * 100 + 30 * 200) / 40  # 175
