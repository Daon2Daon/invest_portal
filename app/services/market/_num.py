import math


def finite(x) -> float | None:
    """비유한(NaN/Inf) 또는 변환 불가 값을 None으로 정제한다."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None
