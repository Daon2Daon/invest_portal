"""가격 알림 순수 평가함수(네트워크/DB 없음)."""


def compute_target(basis: str, direction: str, value: float,
                   basis_price: float | None) -> float:
    """목표가 산출. ABSOLUTE는 value 그대로, 그 외는 기준가×(1±value%)."""
    if basis == "ABSOLUTE":
        return value
    sign = 1.0 if direction == "ABOVE" else -1.0
    return basis_price * (1.0 + sign * value / 100.0)


def is_fired(direction: str, current_price: float, target_price: float) -> bool:
    """ABOVE → 현재가 ≥ 목표가, BELOW → 현재가 ≤ 목표가 (경계 포함)."""
    if direction == "ABOVE":
        return current_price >= target_price
    return current_price <= target_price
