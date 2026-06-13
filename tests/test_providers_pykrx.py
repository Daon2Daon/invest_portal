from unittest.mock import patch
import pandas as pd
from app.services.market.pykrx_provider import PykrxProvider


def _stock_df():
    return pd.DataFrame({"종가": [70000, 71000], "거래량": [100, 200]})


def _etf_df():
    return pd.DataFrame({"종가": [10000, 10100], "거래량": [50, 60]})


@patch("app.services.market.pykrx_provider.stock")
def test_resolve_kr_stock(mock_stock):
    mock_stock.get_etf_ticker_list.return_value = ["069500"]
    mock_stock.get_etn_ticker_list.return_value = []
    mock_stock.get_market_ticker_name.return_value = "삼성전자"
    mock_stock.get_market_ohlcv_by_date.return_value = _stock_df()

    r = PykrxProvider().resolve("005930", "KR")
    assert r.asset_type == "stock"
    assert r.currency == "KRW"
    assert r.fetch_symbol == "005930"
    assert r.current_price == 71000


@patch("app.services.market.pykrx_provider.stock")
def test_resolve_kr_etf_uses_etf_functions(mock_stock):
    mock_stock.get_etf_ticker_list.return_value = ["069500"]
    mock_stock.get_etn_ticker_list.return_value = []
    mock_stock.get_etf_ticker_name.return_value = "KODEX 200"
    mock_stock.get_etf_ohlcv_by_date.return_value = _etf_df()

    r = PykrxProvider().resolve("069500", "KR")
    assert r.asset_type == "etf"
    assert r.current_price == 10100
    mock_stock.get_etf_ohlcv_by_date.assert_called()
    mock_stock.get_market_ohlcv_by_date.assert_not_called()


@patch("app.services.market.pykrx_provider.stock")
def test_resolve_kr_unknown_returns_none(mock_stock):
    mock_stock.get_etf_ticker_list.return_value = []
    mock_stock.get_etn_ticker_list.return_value = []
    mock_stock.get_market_ticker_name.return_value = None
    r = PykrxProvider().resolve("999999", "KR")
    assert r is None
