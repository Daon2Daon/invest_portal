import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.ai import llm_client as lc


def _mock_client(resp):
    client = AsyncMock()
    client.post = AsyncMock(return_value=resp)
    client.get = AsyncMock(return_value=resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, client


def test_normalize_base_url_adds_scheme_and_strips_slash():
    assert lc._normalize_base_url("gw.local:4000/") == "http://gw.local:4000"
    assert lc._normalize_base_url("https://x/") == "https://x"
    assert lc._normalize_base_url("") == ""


def test_pick_text_from_gemini():
    payload = {"candidates": [{"content": {"parts": [{"text": "안녕"}]}}]}
    assert lc._pick_text_from_gemini(payload) == "안녕"
    assert lc._pick_text_from_gemini({"candidates": []}) == ""


@pytest.mark.asyncio
async def test_analyze_images_builds_gemini_request():
    resp = MagicMock(status_code=200)
    resp.json = MagicMock(return_value={"candidates": [{"content": {"parts": [{"text": "분석결과"}]}}]})
    cm, client = _mock_client(resp)
    with patch("app.services.ai.llm_client.httpx.AsyncClient", return_value=cm):
        out = await lc.analyze_images(
            base_url="http://gw", api_key="K", model="gemini/gemini-2.5-flash",
            images=[(b"\x89PNG", "image/png")], prompt="프롬프트",
            temperature=0.4, max_output_tokens=2000)
    assert out == "분석결과"
    args, kwargs = client.post.call_args
    assert args[0] == "http://gw/gemini/v1beta/models/gemini-2.5-flash:generateContent"
    assert kwargs["params"] == {"key": "K"}
    parts = kwargs["json"]["contents"][0]["parts"]
    assert parts[0]["inlineData"]["mimeType"] == "image/png"
    assert parts[-1]["text"] == "프롬프트"
    assert kwargs["json"]["generationConfig"]["maxOutputTokens"] == 2000


@pytest.mark.asyncio
async def test_analyze_images_non200_raises():
    resp = MagicMock(status_code=500, text="boom")
    cm, _ = _mock_client(resp)
    with patch("app.services.ai.llm_client.httpx.AsyncClient", return_value=cm):
        with pytest.raises(lc.LiteLLMError):
            await lc.analyze_images(base_url="http://gw", api_key="K", model="m",
                                    images=[(b"x", "image/png")], prompt="p")


@pytest.mark.asyncio
async def test_analyze_images_missing_key_raises():
    with pytest.raises(lc.LiteLLMError):
        await lc.analyze_images(base_url="http://gw", api_key="", model="m",
                                images=[(b"x", "image/png")], prompt="p")


@pytest.mark.asyncio
async def test_list_models_parses_ids():
    resp = MagicMock(status_code=200)
    resp.json = MagicMock(return_value={"data": [{"id": "gemini/a"}, {"id": "gemini/b"}, {}]})
    cm, client = _mock_client(resp)
    with patch("app.services.ai.llm_client.httpx.AsyncClient", return_value=cm):
        models = await lc.list_models(base_url="http://gw", api_key="K")
    assert models == ["gemini/a", "gemini/b"]
    args, kwargs = client.get.call_args
    assert args[0] == "http://gw/v1/models"
    assert kwargs["headers"] == {"Authorization": "Bearer K"}
