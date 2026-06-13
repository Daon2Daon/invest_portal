from unittest.mock import patch, MagicMock
from app.services.market.resolver import AssetResolver
from app.services.market.types import ResolvedAsset


def _ra(**kw):
    base = dict(ticker="AAPL", name="Apple", asset_type="stock", market="US",
                currency="USD", data_source="yfinance", fetch_symbol="AAPL", current_price=110.0)
    base.update(kw); return ResolvedAsset(**base)


def test_resolver_returns_preview_on_success():
    yf = MagicMock(); yf.resolve.return_value = _ra()
    r = AssetResolver(yfinance=yf, pykrx=MagicMock(), manual=MagicMock())
    out = r.resolve("AAPL", "US")
    assert out.ok is True
    assert out.asset.name == "Apple"
    assert out.tried == ["yfinance"]


def test_resolver_kr_falls_back_to_yfinance():
    pykrx = MagicMock(); pykrx.resolve.return_value = None
    yf = MagicMock(); yf.resolve.return_value = _ra(market="KR", currency="KRW",
                                                    data_source="yfinance", fetch_symbol="005930.KS")
    r = AssetResolver(yfinance=yf, pykrx=pykrx, manual=MagicMock())
    out = r.resolve("005930", "KR")
    assert out.ok is True
    assert out.tried == ["pykrx", "yfinance"]


def test_resolver_reports_failure_with_tried_list():
    yf = MagicMock(); yf.resolve.return_value = None
    pykrx = MagicMock(); pykrx.resolve.return_value = None
    r = AssetResolver(yfinance=yf, pykrx=pykrx, manual=MagicMock())
    out = r.resolve("005930", "KR")
    assert out.ok is False
    assert out.tried == ["pykrx", "yfinance"]
    assert "manual" in out.suggestion.lower()
