"""LiteLLM 게이트웨이 경량 클라이언트(httpx).

- Gemini native passthrough(비전): POST {base_url}/gemini/v1beta/models/{model}:generateContent?key=...
- 모델 목록: GET {base_url}/v1/models
telegram_service와 동일하게 호출마다 AsyncClient를 컨텍스트로 생성(상태/캐시 없음).
"""
import base64
import httpx

_GEMINI_TIMEOUT = httpx.Timeout(300.0, connect=15.0)
_MODELS_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class LiteLLMError(RuntimeError):
    pass


def _normalize_base_url(raw: str) -> str:
    u = (raw or "").strip()
    if not u:
        return ""
    if not u.lower().startswith(("http://", "https://")):
        u = f"http://{u}"
    return u.rstrip("/")


def _pick_text_from_gemini(payload: dict) -> str:
    try:
        candidates = payload.get("candidates") or []
        if not candidates:
            return ""
        parts = (candidates[0].get("content") or {}).get("parts") or []
        if not parts:
            return ""
        return parts[0].get("text") or ""
    except Exception:
        return ""


async def analyze_images(base_url: str, api_key: str, model: str,
                         images: list[tuple[bytes, str]], prompt: str,
                         temperature: float | None = None,
                         max_output_tokens: int | None = None) -> str:
    """Gemini Vision(inlineData base64) 다중 이미지 → 텍스트. 실패 시 LiteLLMError."""
    base = _normalize_base_url(base_url)
    if not base:
        raise LiteLLMError("AI Gateway base_url이 비어 있습니다.")
    if not api_key:
        raise LiteLLMError("AI Gateway api_key가 비어 있습니다.")
    if not images:
        raise LiteLLMError("분석할 이미지가 없습니다.")
    model_id = model.split("/")[-1] if "/" in model else model
    url = f"{base}/gemini/v1beta/models/{model_id}:generateContent"
    parts: list[dict] = []
    for image_bytes, mime_type in images:
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        parts.append({"inlineData": {"mimeType": mime_type, "data": encoded}})
    parts.append({"text": prompt})
    body: dict = {"contents": [{"role": "user", "parts": parts}]}
    gen_cfg: dict = {}
    if temperature is not None:
        gen_cfg["temperature"] = temperature
    if max_output_tokens is not None:
        gen_cfg["maxOutputTokens"] = max_output_tokens
    if gen_cfg:
        body["generationConfig"] = gen_cfg
    async with httpx.AsyncClient(timeout=_GEMINI_TIMEOUT) as client:
        resp = await client.post(url, params={"key": api_key}, json=body)
    if resp.status_code != 200:
        raise LiteLLMError(f"Gemini 이미지 분석 실패: {resp.status_code} - {resp.text}")
    text = _pick_text_from_gemini(resp.json())
    if not text:
        raise LiteLLMError("Gemini 응답에서 텍스트를 찾지 못했습니다.")
    return text


async def list_models(base_url: str, api_key: str) -> list[str]:
    """게이트웨이 /v1/models의 id 목록. 실패 시 LiteLLMError."""
    base = _normalize_base_url(base_url)
    if not base:
        raise LiteLLMError("AI Gateway base_url이 비어 있습니다.")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=_MODELS_TIMEOUT) as client:
        resp = await client.get(f"{base}/v1/models", headers=headers)
    if resp.status_code != 200:
        raise LiteLLMError(f"/v1/models 실패: {resp.status_code} - {resp.text}")
    return [m["id"] for m in (resp.json().get("data") or []) if m.get("id")]
