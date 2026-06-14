from unittest.mock import patch, MagicMock
from app.services.market.resolver import AssetResolver
from app.services.market.types import ResolvedAsset


def _ra(**kw):
    base = dict(ticker="AAPL", name="Apple", asset_type="stock", market="US",
                currency="USD", data_source="yfinance", fetch_symbol="AAPL", current_price=110.0)
    base.update(kw); return ResolvedAsset(**base)


def test_resolver_explicit_type_overrides_detected_type():
    # 소스는 'etf'로 감지했지만 사용자가 '원자재(commodity)'로 명시 → 저장 유형은 사용자 선택을 따른다.
    yf = MagicMock(); yf.resolve.return_value = _ra(asset_type="etf")
    r = AssetResolver(yfinance=yf, pykrx=MagicMock(), manual=MagicMock())
    out = r.resolve("GLD", "US", asset_type_hint="commodity")
    assert out.ok is True
    assert out.asset.asset_type == "commodity"
    # 시세·통화 등 소스 값은 유지
    assert out.asset.current_price == 110.0
    assert out.asset.currency == "USD"


def test_resolver_no_hint_keeps_detected_type():
    yf = MagicMock(); yf.resolve.return_value = _ra(asset_type="etf")
    r = AssetResolver(yfinance=yf, pykrx=MagicMock(), manual=MagicMock())
    out = r.resolve("SPY", "US")
    assert out.asset.asset_type == "etf"


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


from app.services.market.asset_class import default_asset_class


def test_default_asset_class_mapping():
    assert default_asset_class("stock") == "주식"
    assert default_asset_class("etf") == "주식"
    assert default_asset_class("bond") == "채권"
    assert default_asset_class("crypto") == "가상자산"
    assert default_asset_class("commodity") == "원자재"
    assert default_asset_class("etn") == "기타"
    assert default_asset_class(None) == "기타"
    assert default_asset_class("unknown") == "기타"


def test_resolver_fills_asset_class_from_type():
    yf = MagicMock(); yf.resolve.return_value = _ra(asset_type="stock")
    out = AssetResolver(yfinance=yf, pykrx=MagicMock(), manual=MagicMock()).resolve("AAPL", "US")
    assert out.asset.asset_class == "주식"


def test_resolver_bond_hint_fills_asset_class_채권():
    manual = MagicMock()
    manual.resolve.return_value = _ra(asset_type="bond", data_source="manual", current_price=None)
    out = AssetResolver(yfinance=MagicMock(), pykrx=MagicMock(), manual=manual).resolve("KR123", "KR", asset_type_hint="bond")
    assert out.ok is True
    assert out.asset.asset_class == "채권"
