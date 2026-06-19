from app.services.alert.evaluator import compute_target, is_fired


def test_absolute_ignores_basis_price():
    assert compute_target("ABSOLUTE", "ABOVE", 250.0, None) == 250.0
    assert compute_target("ABSOLUTE", "BELOW", 70000.0, None) == 70000.0


def test_purchase_avg_below_15pct():
    assert compute_target("PURCHASE_AVG", "BELOW", 15.0, 100.0) == 85.0


def test_purchase_avg_above_20pct():
    assert compute_target("PURCHASE_AVG", "ABOVE", 20.0, 100.0) == 120.0


def test_week52_high_below_10pct():
    assert compute_target("WEEK52_HIGH", "BELOW", 10.0, 200.0) == 180.0


def test_week52_low_above_20pct():
    assert compute_target("WEEK52_LOW", "ABOVE", 20.0, 100.0) == 120.0


def test_is_fired_above_boundary_inclusive():
    assert is_fired("ABOVE", 100.0, 100.0) is True
    assert is_fired("ABOVE", 99.9, 100.0) is False


def test_is_fired_below_boundary_inclusive():
    assert is_fired("BELOW", 100.0, 100.0) is True
    assert is_fired("BELOW", 100.1, 100.0) is False
