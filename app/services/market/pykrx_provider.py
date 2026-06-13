from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from pykrx import stock
from app.services.market.types import ResolvedAsset, Quote


def _today_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")


def _window_start() -> str:
    return (datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=10)).strftime("%Y%m%d")


class PykrxProvider:
    """KR 전용. ETF/ETN/주식을 리스트 멤버십으로 판정해 올바른 함수를 호출한다."""

    def _classify(self, ticker: str) -> str:
        today = _today_kst()
        try:
            if ticker in set(stock.get_etf_ticker_list(today)):
                return "etf"
        except Exception:
            pass
        try:
            if ticker in set(stock.get_etn_ticker_list(today)):
                return "etn"
        except Exception:
            pass
        return "stock"

    def _ohlcv(self, ticker: str, asset_type: str):
        start, end = _window_start(), _today_kst()
        if asset_type == "etf":
            return stock.get_etf_ohlcv_by_date(start, end, ticker)
        if asset_type == "etn":
            return stock.get_etn_ohlcv_by_date(start, end, ticker)
        return stock.get_market_ohlcv_by_date(start, end, ticker)

    def _name(self, ticker: str, asset_type: str):
        if asset_type == "etf":
            return stock.get_etf_ticker_name(ticker)
        if asset_type == "etn":
            return stock.get_etn_ticker_name(ticker)
        return stock.get_market_ticker_name(ticker)

    def resolve(self, ticker, market, asset_type_hint=None):
        ticker = ticker.strip()
        asset_type = self._classify(ticker)
        try:
            name = self._name(ticker, asset_type)
            if not name or not isinstance(name, str):
                return None
            df = self._ohlcv(ticker, asset_type)
            if df is None or df.empty:
                return None
            price = float(df["종가"].iloc[-1])
            return ResolvedAsset(
                ticker=ticker, name=name, asset_type=asset_type, market="KR",
                currency="KRW", data_source="pykrx", fetch_symbol=ticker,
                current_price=price,
            )
        except Exception:
            return None

    def quote(self, fetch_symbol, currency, asset_type):
        try:
            df = self._ohlcv(fetch_symbol, asset_type)
            if df is None or df.empty:
                return Quote(price=0.0, currency="KRW", status="error")
            price = float(df["종가"].iloc[-1])
            change = change_pct = None
            if len(df) >= 2:
                prev = float(df["종가"].iloc[-2])
                if prev:
                    change = price - prev
                    change_pct = change / prev * 100
            vol = float(df["거래량"].iloc[-1]) if "거래량" in df else None
            return Quote(price=price, currency="KRW", change=change,
                         change_pct=change_pct, volume=vol, as_of=date.today(), status="ok")
        except Exception:
            return Quote(price=0.0, currency="KRW", status="error")
