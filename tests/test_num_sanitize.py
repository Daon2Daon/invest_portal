import math
from unittest.mock import MagicMock, patch
import pandas as pd
from app.services.market._num import finite
from app.services.market.yfinance_provider import YFinanceProvider


def test_finite_passes_through_normal():
    assert finite(110.0) == 110.0
    assert finite(0) == 0.0


def test_finite_rejects_nan_inf_and_none():
    assert finite(float("nan")) is None
    assert finite(float("inf")) is None
    assert finite(None) is None
    assert finite("x") is None


@patch("app.services.market.yfinance_provider.yf.Ticker")
def test_yfinance_quote_nan_close_is_error(mock_ticker):
    inst = MagicMock()
    inst.history.return_value = pd.DataFrame({"Close": [100.0, float("nan")], "Volume": [10, 20]})
    mock_ticker.return_value = inst
    q = YFinanceProvider().quote("AAPL", "USD", "stock")
    assert q.status == "error"
    assert q.price == 0.0
