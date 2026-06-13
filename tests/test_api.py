import pytest
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_resolve_endpoint_returns_preview():
    from app.services.market.types import ResolvedAsset
    from app.services.market.resolver import ResolveResult
    fake = ResolveResult(ok=True, asset=ResolvedAsset(
        ticker="AAPL", name="Apple", asset_type="stock", market="US", currency="USD",
        data_source="yfinance", fetch_symbol="AAPL", current_price=110.0), tried=["yfinance"])
    with patch("app.routers.assets._resolver.resolve", return_value=fake):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            resp = await ac.post("/api/assets/resolve",
                                 json={"ticker": "AAPL", "market": "US"})
    assert resp.status_code == 200
    assert resp.json()["asset"]["name"] == "Apple"
