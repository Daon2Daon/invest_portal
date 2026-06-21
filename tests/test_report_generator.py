import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.ai_report import report_generator as rg


def _settings(values: dict):
    async def fake(db, category, key):
        return values.get((category, key))
    return fake


@pytest.mark.asyncio
async def test_load_config_disabled_raises():
    vals = {("ai_report", "enabled"): "false"}
    with patch("app.services.ai_report.report_generator.get_setting", _settings(vals)):
        with pytest.raises(rg.ReportDisabled):
            await rg.load_config(MagicMock())


@pytest.mark.asyncio
async def test_load_config_missing_keys_raises():
    vals = {("ai_report", "enabled"): "true", ("ai_gateway", "base_url"): "http://gw"}
    with patch("app.services.ai_report.report_generator.get_setting", _settings(vals)):
        with pytest.raises(rg.ReportNotConfigured):
            await rg.load_config(MagicMock())


@pytest.mark.asyncio
async def test_load_config_ok_uses_default_prompt():
    vals = {("ai_report", "enabled"): "true",
            ("ai_gateway", "base_url"): "http://gw",
            ("ai_gateway", "api_key"): "K",
            ("ai_report", "model"): "gemini/x"}
    with patch("app.services.ai_report.report_generator.get_setting", _settings(vals)):
        cfg = await rg.load_config(MagicMock())
    assert cfg["base_url"] == "http://gw" and cfg["model"] == "gemini/x"
    assert cfg["prompt"] == rg.DEFAULT_PROMPT


@pytest.mark.asyncio
async def test_generate_markdown_calls_llm():
    cfg = {"base_url": "http://gw", "api_key": "K", "model": "gemini/x", "prompt": "지시"}
    with patch("app.services.ai_report.report_generator.load_config", AsyncMock(return_value=cfg)), \
         patch("app.services.ai_report.report_generator.report_data.collect_input_block",
               AsyncMock(return_value="## 데이터블록")), \
         patch("app.services.ai_report.report_generator.llm_client.generate_text",
               AsyncMock(return_value="## 리포트")) as gt:
        md, model = await rg.generate_markdown(MagicMock())
    assert md == "## 리포트" and model == "gemini/x"
    prompt_arg = gt.call_args.kwargs["prompt"]
    assert "지시" in prompt_arg and "## 데이터블록" in prompt_arg


@pytest.mark.asyncio
async def test_create_report_stores_row():
    with patch("app.services.ai_report.report_generator.generate_markdown",
               AsyncMock(return_value=("## 리포트", "gemini/x"))), \
         patch("app.services.ai_report.report_generator.report_store.create",
               AsyncMock(return_value="ROW")) as cr:
        out = await rg.create_report(MagicMock(), trigger="scheduled")
    assert out == "ROW"
    assert cr.call_args.args[4] == "scheduled"   # trigger 인자
