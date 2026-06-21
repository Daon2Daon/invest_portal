import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.risk_signal import risk_service as rs


def _settings(values: dict):
    async def fake(db, category, key):
        return values.get((category, key))
    return fake


@pytest.mark.asyncio
async def test_load_config_defaults_when_unset():
    with patch("app.services.risk_signal.risk_service.get_setting", _settings({})):
        cfg = await rs.load_config(MagicMock())
    assert cfg["enabled"] is False
    assert cfg["sig_rsi"] is True and cfg["sig_concentration_class"] is True
    assert cfg["threshold_asset_pct"] == 30.0 and cfg["threshold_class_pct"] == 60.0


@pytest.mark.asyncio
async def test_load_config_reads_stored_values():
    vals = {("risk_signal", "enabled"): "true", ("risk_signal", "sig_rsi"): "false",
            ("risk_signal", "threshold_asset_pct"): "25"}
    with patch("app.services.risk_signal.risk_service.get_setting", _settings(vals)):
        cfg = await rs.load_config(MagicMock())
    assert cfg["enabled"] is True and cfg["sig_rsi"] is False
    assert cfg["threshold_asset_pct"] == 25.0


@pytest.mark.asyncio
async def test_build_digest_uses_scanner_and_message():
    with patch("app.services.risk_signal.risk_service.load_config", AsyncMock(return_value={"x": 1})), \
         patch("app.services.risk_signal.risk_service.scanner.scan",
               AsyncMock(return_value=[{"category": "concentration", "type": "종목 과중",
                                        "name": "삼성(005930)", "detail": "62.0%"}])):
        out = await rs.build_digest(MagicMock())
    assert "비중 편향" in out and "종목 과중" in out


@pytest.mark.asyncio
async def test_build_and_send_calls_telegram():
    with patch("app.services.risk_signal.risk_service.build_digest", AsyncMock(return_value="msg")), \
         patch("app.services.risk_signal.risk_service.telegram_service.send_message",
               AsyncMock(return_value=True)) as sm:
        out = await rs.build_and_send(MagicMock())
    assert out["sent"] is True
    sm.assert_awaited_once()
