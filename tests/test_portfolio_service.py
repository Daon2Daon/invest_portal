from app.services.portfolio.portfolio_service import aggregate_position
from app.services.portfolio.portfolio_service import build_allocation


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


def test_build_allocation_groups_by_class_and_adds_cash():
    positions = [
        {"asset_class": "주식", "value_krw": 600.0},
        {"asset_class": "채권", "value_krw": 300.0},
        {"asset_class": "주식", "value_krw": 100.0},
    ]
    total_cash = 200.0
    total_value = 1200.0  # 1000 종목 + 200 현금
    alloc = build_allocation(positions, total_cash, total_value)
    by = {a["asset_class"]: a for a in alloc}
    assert by["주식"]["value_krw"] == 700.0
    assert round(by["주식"]["weight_pct"], 4) == round(700/1200*100, 4)
    assert by["채권"]["value_krw"] == 300.0
    assert by["현금성"]["value_krw"] == 200.0
    assert [a["asset_class"] for a in alloc] == ["주식", "채권", "현금성"]


def test_build_allocation_null_class_is_기타():
    alloc = build_allocation([{"asset_class": None, "value_krw": 50.0}], 0.0, 50.0)
    assert alloc[0]["asset_class"] == "기타"
    assert alloc[0]["weight_pct"] == 100.0
