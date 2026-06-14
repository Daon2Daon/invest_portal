from app.services.portfolio.portfolio_service import aggregate_position


def test_aggregate_position_single_lot_krw():
    lots = [dict(quantity=10, purchase_price=70000, fee=0)]
    pos = aggregate_position(lots, current_price=71000, fx_now=1.0)
    assert pos["quantity"] == 10
    assert pos["avg_price"] == 70000
    assert pos["cost_native"] == 700000
    assert pos["value_native"] == 710000
    assert pos["cost_krw"] == 700000
    assert pos["value_krw"] == 710000
    assert pos["profit_loss_krw"] == 10000
    assert round(pos["profit_loss_pct"], 4) == round(10000 / 700000 * 100, 4)


def test_aggregate_position_usd_uses_current_fx_for_both_cost_and_value():
    # 매수시점 환율을 쓰지 않는다: 원가·평가액 모두 현재 환율(1350)로 환산.
    lots = [dict(quantity=10, purchase_price=100, fee=0)]
    pos = aggregate_position(lots, current_price=110, fx_now=1350.0)
    assert pos["cost_native"] == 1000
    assert pos["value_native"] == 1100
    assert pos["profit_loss_native"] == 100
    assert pos["cost_krw"] == 1350000
    assert pos["value_krw"] == 1485000
    assert pos["profit_loss_krw"] == 135000
    assert pos["profit_loss_pct"] == 10.0


def test_aggregate_position_fee_added_to_cost():
    lots = [dict(quantity=10, purchase_price=100, fee=50)]
    pos = aggregate_position(lots, current_price=100, fx_now=1.0)
    assert pos["cost_native"] == 1050  # 1000 + 50 수수료
    assert pos["value_native"] == 1000
    assert pos["profit_loss_native"] == -50


def test_aggregate_position_multi_lot_weighted_avg():
    lots = [
        dict(quantity=10, purchase_price=100, fee=0),
        dict(quantity=30, purchase_price=200, fee=0),
    ]
    pos = aggregate_position(lots, current_price=200, fx_now=1.0)
    assert pos["quantity"] == 40
    assert pos["avg_price"] == (10 * 100 + 30 * 200) / 40  # 175
