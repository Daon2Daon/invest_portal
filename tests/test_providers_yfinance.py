from unittest.mock import MagicMock, patch
import pandas as pd
from app.services.market.yfinance_provider import YFinanceProvider


def _fake_hist():
    return pd.DataFrame({"Close": [100.0, 110.0], "Volume": [10, 20]})


@patch("app.services.market.yfinance_provider.yf.Ticker")
def test_resolve_us_equity(mock_ticker):
    inst = MagicMock()
    inst.history.return_value = _fake_hist()
    inst.info = {"quoteType": "EQUITY", "longName": "Apple Inc.", "currency": "USD"}
    mock_ticker.return_value = inst

    p = YFinanceProvider()
    r = p.resolve("AAPL", "US")
    assert r is not None
    assert r.fetch_symbol == "AAPL"
    assert r.asset_type == "stock"
    assert r.currency == "USD"
    assert r.current_price == 110.0


@patch("app.services.market.yfinance_provider.yf.Ticker")
def test_resolve_jp_appends_t_suffix(mock_ticker):
    inst = MagicMock()
    inst.history.return_value = _fake_hist()
    inst.info = {"quoteType": "EQUITY", "longName": "Toyota", "currency": "JPY"}
    mock_ticker.return_value = inst

    p = YFinanceProvider()
    r = p.resolve("7203", "JP")
    assert r.fetch_symbol == "7203.T"
    assert r.currency == "JPY"


@patch("app.services.market.yfinance_provider.yf.Ticker")
def test_resolve_crypto_appends_usd(mock_ticker):
    inst = MagicMock()
    inst.history.return_value = _fake_hist()
    inst.info = {"quoteType": "CRYPTOCURRENCY", "shortName": "Bitcoin", "currency": "USD"}
    mock_ticker.return_value = inst

    p = YFinanceProvider()
    r = p.resolve("BTC", "CRYPTO")
    assert r.fetch_symbol == "BTC-USD"
    assert r.asset_type == "crypto"


@patch("app.services.market.yfinance_provider.yf.Ticker")
def test_resolve_returns_none_on_empty_history(mock_ticker):
    inst = MagicMock()
    inst.history.return_value = pd.DataFrame()
    inst.info = {}
    mock_ticker.return_value = inst

    p = YFinanceProvider()
    assert p.resolve("NOPE", "US") is None
