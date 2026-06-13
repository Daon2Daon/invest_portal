from app.services.market.yfinance_provider import YFinanceProvider
from app.services.market.pykrx_provider import PykrxProvider
from app.services.market.manual_provider import ManualProvider


class ProviderRegistry:
    def __init__(self):
        self.yfinance = YFinanceProvider()
        self.pykrx = PykrxProvider()
        self.manual = ManualProvider()

    def for_source(self, data_source: str):
        return {"yfinance": self.yfinance, "pykrx": self.pykrx, "manual": self.manual}[data_source]


registry = ProviderRegistry()
