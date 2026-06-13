from datetime import date
from app.services.market.types import ResolvedAsset, Quote


class ManualProvider:
    """무료 API에 시세가 없는 자산(개별 채권 등). 사용자가 입력한 manual_price를 그대로 사용."""

    def resolve(self, ticker, market, asset_type_hint=None):
        ticker = ticker.strip().upper()
        currency = {"US": "USD", "JP": "JPY", "KR": "KRW"}.get(market, "KRW")
        return ResolvedAsset(
            ticker=ticker, name=ticker, asset_type=asset_type_hint or "bond",
            market=market, currency=currency, data_source="manual",
            fetch_symbol=ticker, current_price=None,
        )

    def quote(self, fetch_symbol, currency, asset_type, manual_price=None):
        if manual_price is None:
            return Quote(price=0.0, currency=currency, status="stale")
        return Quote(price=float(manual_price), currency=currency, as_of=date.today(), status="ok")
