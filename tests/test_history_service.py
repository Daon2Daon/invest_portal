import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import pandas as pd
from app.services.market.history_service import get_history


@pytest.mark.asyncio
async def test_get_history_dispatches_by_data_source():
    asset = SimpleNamespace(data_source="yfinance", fetch_symbol="AAPL", market="US")
    fake = pd.DataFrame({"Open":[1],"High":[1],"Low":[1],"Close":[1],"Volume":[1]})
    with patch("app.services.market.history_service.registry") as reg:
        reg.for_source.return_value = MagicMock(history=MagicMock(return_value=fake))
        df = await get_history(asset, 365)
        reg.for_source.assert_called_once_with("yfinance")
        assert df is not None and len(df) == 1


@pytest.mark.asyncio
async def test_get_history_none_passthrough():
    asset = SimpleNamespace(data_source="manual", fetch_symbol="X", market="KR")
    with patch("app.services.market.history_service.registry") as reg:
        reg.for_source.return_value = MagicMock(history=MagicMock(return_value=None))
        assert await get_history(asset, 365) is None
