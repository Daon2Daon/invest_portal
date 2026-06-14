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


@patch("app.services.market.yfinance_provider.yf.Ticker")
def test_resolve_kr_uses_ks_suffix(mock_ticker):
    # KR 폴백: {ticker}.KS 를 먼저 시도해 해석(통화 KRW). KR ETF가 pykrx 실패 시 yfinance로 잡힘.
    def fake(sym):
        inst = MagicMock()
        if sym == "385560.KS":
            inst.history.return_value = pd.DataFrame({"Close": [100.0, 55245.0], "Volume": [1, 2]})
            inst.info = {"quoteType": "ETF", "longName": "RISE KIS Bond ETF", "currency": "KRW"}
        else:
            inst.history.return_value = pd.DataFrame()
            inst.info = {}
        return inst
    mock_ticker.side_effect = fake

    r = YFinanceProvider().resolve("385560", "KR")
    assert r is not None
    assert r.fetch_symbol == "385560.KS"
    assert r.market == "KR"
    assert r.currency == "KRW"
    assert r.asset_type == "etf"
    assert r.current_price == 55245.0


@patch("app.services.market.yfinance_provider.yf.Ticker")
def test_resolve_kr_falls_back_to_kq(mock_ticker):
    # .KS 에 데이터가 없으면 .KQ 를 시도한다.
    def fake(sym):
        inst = MagicMock()
        if sym == "123456.KQ":
            inst.history.return_value = pd.DataFrame({"Close": [100.0, 200.0], "Volume": [1, 2]})
            inst.info = {"quoteType": "EQUITY", "shortName": "코스닥종목", "currency": "KRW"}
        else:
            inst.history.return_value = pd.DataFrame()
            inst.info = {}
        return inst
    mock_ticker.side_effect = fake

    r = YFinanceProvider().resolve("123456", "KR")
    assert r is not None
    assert r.fetch_symbol == "123456.KQ"
    assert r.currency == "KRW"
