from unittest.mock import patch, MagicMock
import pandas as pd
from app.services.market.yfinance_provider import YFinanceProvider
from app.services.market.pykrx_provider import PykrxProvider
from app.services.market.manual_provider import ManualProvider


@patch("app.services.market.yfinance_provider.yf.Ticker")
def test_yfinance_history_returns_ohlcv(mock_ticker):
    inst = MagicMock()
    inst.history.return_value = pd.DataFrame({
        "Open": [1.0, 2.0], "High": [2, 3], "Low": [0.5, 1], "Close": [1.5, 2.5],
        "Volume": [10, 20], "Dividends": [0, 0]})
    mock_ticker.return_value = inst
    df = YFinanceProvider().history("AAPL", "US", 365)
    assert df is not None and len(df) == 2
    assert {"Open", "High", "Low", "Close", "Volume"} <= set(df.columns)


@patch("app.services.market.pykrx_provider.stock")
def test_pykrx_history_renames_korean_cols(mock_stock):
    mock_stock.get_market_ohlcv_by_date.return_value = pd.DataFrame({
        "시가": [70000], "고가": [71000], "저가": [69000], "종가": [70500], "거래량": [100]})
    df = PykrxProvider().history("005930", "KR", 365)
    assert df is not None
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df["Close"].iloc[-1] == 70500


def test_manual_history_is_none():
    assert ManualProvider().history("X", "KR", 365) is None
