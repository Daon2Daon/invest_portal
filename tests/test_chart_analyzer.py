import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.ai import chart_analyzer as ca


def test_md_to_telegram_html_converts():
    out = ca._md_to_telegram_html("# 제목\n**굵게** *기울임* `코드`")
    assert "<b>제목</b>" in out
    assert "<b>굵게</b>" in out
    assert "<i>기울임</i>" in out
    assert "<code>코드</code>" in out


def test_md_to_telegram_html_strips_unsupported_tags():
    out = ca._md_to_telegram_html("<ul><li>항목</li></ul>")
    assert "<ul>" not in out and "<li>" not in out
    assert "항목" in out


def test_split_message_splits_long_text():
    text = "\n".join(["x" * 100 for _ in range(60)])  # ~6000자
    parts = ca._split_message(text, limit=4000)
    assert len(parts) >= 2
    assert all(len(p) <= 4000 for p in parts)


def test_split_message_short_returns_single():
    assert ca._split_message("짧은 글") == ["짧은 글"]


def test_build_prompt_prepends_meta_and_appends_format():
    p = ca._build_prompt("USER", "AAPL", "Apple", "US", ["일봉 (1년)", "주봉 (5년)"])
    assert "AAPL" in p and "Apple" in p and "US" in p
    assert "USER" in p
    assert "<b>" in p  # 텔레그램 포맷 지시 포함


@pytest.mark.asyncio
async def test_load_config_disabled_raises():
    db = MagicMock()
    with patch.object(ca, "get_setting", AsyncMock(return_value="false")):
        with pytest.raises(ca.AnalysisDisabled):
            await ca.load_config(db)


@pytest.mark.asyncio
async def test_load_config_missing_keys_raises():
    db = MagicMock()

    async def fake_get(_db, _cat, key):
        return {"enabled": "true"}.get(key)  # base_url/api_key/model 모두 None

    with patch.object(ca, "get_setting", AsyncMock(side_effect=fake_get)):
        with pytest.raises(ca.AnalysisNotConfigured):
            await ca.load_config(db)


@pytest.mark.asyncio
async def test_load_config_defaults_prompt():
    db = MagicMock()

    async def fake_get(_db, _cat, key):
        return {"enabled": "true", "base_url": "http://gw",
                "api_key": "K", "model": "m"}.get(key)  # prompt None

    with patch.object(ca, "get_setting", AsyncMock(side_effect=fake_get)):
        cfg = await ca.load_config(db)
    assert cfg["prompt"] == ca.DEFAULT_PROMPT
    assert cfg["base_url"] == "http://gw"


@pytest.mark.asyncio
async def test_analyze_calls_client_and_formats():
    db = MagicMock()
    cfg = {"base_url": "http://gw", "api_key": "K", "model": "m", "prompt": "P"}
    with patch.object(ca, "load_config", AsyncMock(return_value=cfg)), \
         patch.object(ca.llm_client, "analyze_images",
                      AsyncMock(return_value="**요약**")) as mock_ai:
        parts = await ca.analyze(db, [(b"d", "image/png"), (b"w", "image/png")],
                                 "AAPL", "Apple", "US")
    assert parts == ["<b>요약</b>"]
    _, kwargs = mock_ai.call_args
    assert len(kwargs["images"]) == 2
    assert kwargs["base_url"] == "http://gw"
