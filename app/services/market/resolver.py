from dataclasses import dataclass, field
from app.services.market.types import ResolvedAsset
from app.services.market.registry import registry

# 시장별 해석 체인 (provider 속성명 순서)
_CHAINS = {
    "US": ["yfinance"],
    "JP": ["yfinance"],
    "CRYPTO": ["yfinance"],
    "KR": ["pykrx", "yfinance"],
}


@dataclass
class ResolveResult:
    ok: bool
    asset: ResolvedAsset | None = None
    tried: list[str] = field(default_factory=list)
    suggestion: str = ""


class AssetResolver:
    def __init__(self, yfinance=None, pykrx=None, manual=None):
        self.providers = {
            "yfinance": yfinance or registry.yfinance,
            "pykrx": pykrx or registry.pykrx,
            "manual": manual or registry.manual,
        }

    def resolve(self, ticker: str, market: str, asset_type_hint: str | None = None) -> ResolveResult:
        # 채권/수동 요청은 바로 manual.
        if asset_type_hint == "bond":
            asset = self.providers["manual"].resolve(ticker, market, asset_type_hint)
            return ResolveResult(ok=True, asset=asset, tried=["manual"])
        tried: list[str] = []
        for name in _CHAINS.get(market, ["yfinance"]):
            tried.append(name)
            asset = self.providers[name].resolve(ticker, market, asset_type_hint)
            if asset is not None:
                # 사용자가 유형을 명시했으면 저장 유형으로 존중한다.
                # (시세·통화·이름·fetch_symbol은 데이터 소스가 채운 값을 유지)
                if asset_type_hint:
                    asset.asset_type = asset_type_hint
                return ResolveResult(ok=True, asset=asset, tried=tried)
        return ResolveResult(
            ok=False, tried=tried,
            suggestion="자동 조회 실패. 티커·시장을 확인하거나 수동(manual) 모드로 등록하세요.",
        )
