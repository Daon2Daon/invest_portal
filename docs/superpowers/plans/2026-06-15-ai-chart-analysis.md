# 2c: AI 차트 분석 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 차트 PNG(일봉+주봉)를 비전 LLM(Gemini native passthrough)으로 분석해 기술적 코멘트를 생성하고, 차트 화면에서 미리보거나 텔레그램으로 차트와 함께 발송한다.

**Architecture:** 신규 `app/services/ai/` 패키지에 transport(`llm_client.py`, httpx)와 도메인(`chart_analyzer.py`, 프롬프트·HTML변환)을 분리한다. 설정은 기존 `app_settings`의 `ai_gateway` 카테고리에 `settings_manager`로 저장(신규 마이그레이션 없음). 라우터는 `settings.py`(AI 엔드포인트)·`charts.py`(analyze + send-telegram 통합)를 확장한다.

**Tech Stack:** FastAPI, async SQLAlchemy, httpx, pytest/pytest-asyncio, React+Vite+TS.

**테스트 실행 환경변수(통합/스모크):**
```
SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q
```
단위 테스트(httpx mock, DB 불필요)는 환경변수 없이도 동작한다.

---

## Task 1: LLM transport (`app/services/ai/llm_client.py`)

**Files:**
- Create: `app/services/ai/__init__.py`
- Create: `app/services/ai/llm_client.py`
- Test: `tests/test_ai_llm_client.py`

- [ ] **Step 1: 빈 패키지 init 생성**

`app/services/ai/__init__.py` 빈 파일로 생성:

```python
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_ai_llm_client.py`:

```python
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
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_ai_llm_client.py -q`
Expected: FAIL (ModuleNotFoundError: app.services.ai.llm_client)

- [ ] **Step 4: 구현**

`app/services/ai/llm_client.py`:

```python
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
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_ai_llm_client.py -q`
Expected: PASS (7 passed)

- [ ] **Step 6: 커밋**

```bash
git add app/services/ai/__init__.py app/services/ai/llm_client.py tests/test_ai_llm_client.py
git commit -m "feat(ai): LiteLLM gemini-native vision client + model listing

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: 도메인 분석기 (`app/services/ai/chart_analyzer.py`)

**Files:**
- Create: `app/services/ai/chart_analyzer.py`
- Test: `tests/test_chart_analyzer.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_chart_analyzer.py`:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_chart_analyzer.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 구현**

`app/services/ai/chart_analyzer.py` (DEFAULT_PROMPT·HTML변환은 my-assistant `chart_analyzer.py`에서 이식):

```python
"""차트 이미지 → AI 기술분석 텍스트(텔레그램 HTML). 설정은 ai_gateway 카테고리."""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings.settings_manager import get_setting
from app.services.ai import llm_client

CATEGORY = "ai_gateway"
_TEMPERATURE = 0.4
_MAX_OUTPUT_TOKENS = 2000


class AnalysisNotConfigured(Exception):
    pass


class AnalysisDisabled(Exception):
    pass


DEFAULT_PROMPT = """# 역할
- 당신은 자산운용사 트레이딩 데스크에서 10년 이상 차트 분석을 담당한 시니어 차티스트입니다.
- 매일 아침 운용역에게 텔레그램으로 자산의 기술적 관점을 보고합니다.

# 입력 차트 구성 (매우 중요 — 정확한 해석을 위해 숙지)
제공되는 각 차트는 4개 패널로 구성됩니다.

[Panel 1 - 가격 차트]
- 캔들스틱 (녹색=상승, 적색=하락)
- 이동평균선 4종: EMA 12(빨강), EMA 26(파랑), SMA 20(진녹), SMA 50(주황)
- 볼린저밴드 (회색 점선 ±2σ, 음영 영역)

[Panel 2 - RSI(14)]
- 보라색 선, 70 이상 과매수, 30 이하 과매도
- (배경의 옅은 노란색은 30-70 중립구간 표시일 뿐)

[Panel 3 - MACD]
- 파랑 = MACD (EMA12 - EMA26), 빨강 = Signal(9-period EMA), 막대 = Histogram

[Panel 4 - 거래량]
- 막대 = 거래량(상승 녹색/하락 적색), 파랑선 = 거래량 20기간 이동평균

# 분석 원칙
- 매크로/펀더멘털/밸류에이션은 일체 고려하지 않습니다. 오직 차트의 가격 행동과 위 지표만으로 판단합니다.
- 일봉(단기)과 주봉(중장기)이 함께 제공되면 반드시 교차 분석하여 신호의 일치/괴리를 명시합니다.
- 일반론을 피하고 차트에서 읽히는 구체적 근거(가격대, 지표값, 패턴)를 인용합니다.

# 출력 구조 (이 순서·헤더 유지)
1. **종합 의견 한 줄** — 추세 단계 + 모멘텀 + 단기 편향
2. **주봉 관점 (중장기)** — 큰 흐름, 핵심 매물대, 이평선 배열, 보조지표
3. **일봉 관점 (단기)** — 최근 캔들 패턴, 이평선 정/역배열, 볼린저 위치, RSI/MACD
4. **시간프레임 통합 진단** — 일봉·주봉 신호 일치/괴리, 우세한 방향
5. **시나리오** — 상승/하락 시나리오 각각의 트리거 가격과 1차 목표/이탈 대응
6. **트레이딩 관점** — 매수/매도/관망 판단, 핵심 관찰 가격대, 주요 리스크

# 출력 형식
- 개조식(불릿 위주), 가격은 차트에서 읽히는 수준으로 표기
- 단정적 예측 대신 조건부 시나리오로 작성(예: "X 돌파 시 → Y 시도")
- 전체 분량: 한글 1,500~2,500자 권장"""

_TELEGRAM_FORMAT_INSTRUCTION = """

[출력 형식 제한]
- 텔레그램 발송용이므로 아래 HTML 태그만 사용: <b>, <i>, <code>, <pre>
- 헤딩(#, ##)은 <b>섹션명</b> 형태로, **굵게**는 <b>굵게</b>, *기울임*은 <i>기울임</i>
- 불릿(-)은 그대로 유지, 1200자 이내 권장"""


def _md_to_telegram_html(text: str) -> str:
    text = re.sub(r"```[a-zA-Z]*\n?([\s\S]*?)```", r"<pre>\1</pre>", text)
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*([^*\n]+)\*", r"<i>\1</i>", text)
    text = re.sub(r"^#{1,3}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"<(h[1-6]|ul|ol|li|hr|br|div|span|p)\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</(h[1-6]|ul|ol|li|hr|br|div|span|p)\b>", "", text, flags=re.IGNORECASE)
    return text.strip()


def _split_message(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, current, current_len = [], [], 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > limit and current:
            parts.append("".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += len(line)
    if current:
        parts.append("".join(current))
    return parts


def _build_prompt(user_prompt: str, ticker: str, name: str, market: str,
                  chart_labels: list[str]) -> str:
    now_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M KST")
    image_order = "\n".join(f"  - 이미지 {i+1}: {label}" for i, label in enumerate(chart_labels))
    multi_tf = ("\n- 일봉과 주봉이 함께 제공되었으므로 단기/중장기 흐름을 교차 분석해 방향성의 일치/괴리를 반드시 언급하세요."
                if len(chart_labels) >= 2 else "")
    meta = (
        f"[종목 정보]\n- 종목명: {name}\n- 티커: {ticker}\n- 시장: {market}\n- 분석 시점: {now_kst}\n\n"
        f"[제공된 차트 이미지 순서]\n{image_order}{multi_tf}\n\n[분석 지시]\n"
    )
    return meta + user_prompt + _TELEGRAM_FORMAT_INSTRUCTION


async def load_config(db: AsyncSession) -> dict:
    """ai_gateway 설정 로드. 비활성→AnalysisDisabled, 필수키 누락→AnalysisNotConfigured."""
    enabled = (await get_setting(db, CATEGORY, "enabled")) or "false"
    if enabled.lower() != "true":
        raise AnalysisDisabled("AI 분석이 비활성화되어 있습니다.")
    base_url = await get_setting(db, CATEGORY, "base_url")
    api_key = await get_setting(db, CATEGORY, "api_key")
    model = await get_setting(db, CATEGORY, "model")
    if not base_url or not api_key or not model:
        raise AnalysisNotConfigured("AI 게이트웨이 설정(base_url/api_key/model)이 비어 있습니다.")
    prompt = (await get_setting(db, CATEGORY, "prompt")) or DEFAULT_PROMPT
    return {"base_url": base_url, "api_key": api_key, "model": model, "prompt": prompt}


async def analyze(db: AsyncSession, images: list[tuple[bytes, str]],
                  ticker: str, name: str, market: str) -> list[str]:
    """이미지(일봉,주봉 순) → 텔레그램 HTML 메시지 조각 리스트. 미설정/비활성/실패는 예외 전파."""
    cfg = await load_config(db)
    chart_labels = ["일봉 (1년)", "주봉 (5년)"][:len(images)]
    prompt = _build_prompt(cfg["prompt"], ticker, name, market, chart_labels)
    raw = await llm_client.analyze_images(
        base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"],
        images=images, prompt=prompt,
        temperature=_TEMPERATURE, max_output_tokens=_MAX_OUTPUT_TOKENS)
    return _split_message(_md_to_telegram_html(raw))
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_chart_analyzer.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: 커밋**

```bash
git add app/services/ai/chart_analyzer.py tests/test_chart_analyzer.py
git commit -m "feat(ai): chart analyzer (prompt build, md->telegram html, config gating)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 설정 라우터 AI 엔드포인트 (`app/routers/settings.py`)

**Files:**
- Modify: `app/routers/settings.py`
- Test: `tests/test_settings_ai.py`

**중요(라우트 순서):** `/ai`·`/ai/models`는 반드시 기존 `/{category}/{key}` 제너릭 라우트보다 **먼저** 선언해야 한다(`/ai/models`가 `/{category}/{key}`에 가로채이지 않도록). 기존 `/telegram` 라우트들이 이미 제너릭 앞에 있으므로, AI 라우트를 그 블록(제너릭 `read`/`write` 정의 위)에 추가한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_settings_ai.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from app.main import app


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_get_ai_masks_api_key():
    async def fake_get(_db, _cat, key):
        return {"base_url": "http://gw", "api_key": "SECRET",
                "model": "m", "prompt": "P", "enabled": "true"}.get(key)
    with patch("app.routers.settings.get_setting", AsyncMock(side_effect=fake_get)):
        async with await _client() as ac:
            resp = await ac.get("/api/settings/ai")
    body = resp.json()
    assert resp.status_code == 200
    assert body["api_key_set"] is True
    assert "api_key" not in body
    assert body["base_url"] == "http://gw"
    assert body["enabled"] is True


@pytest.mark.asyncio
async def test_put_ai_skips_empty_api_key():
    calls = []

    async def fake_set(_db, cat, key, value, is_secret=False, value_type="string"):
        calls.append((key, value, is_secret))

    with patch("app.routers.settings.set_setting", AsyncMock(side_effect=fake_set)):
        async with await _client() as ac:
            resp = await ac.put("/api/settings/ai", json={
                "base_url": "http://gw", "api_key": "", "model": "m", "enabled": True})
    assert resp.status_code == 200
    keys = [c[0] for c in calls]
    assert "api_key" not in keys          # 빈 키는 저장 생략
    assert ("base_url", "http://gw", False) in calls
    assert ("enabled", "true", False) in calls


@pytest.mark.asyncio
async def test_ai_models_returns_error_when_no_base_url():
    async def fake_get(_db, _cat, key):
        return None
    with patch("app.routers.settings.get_setting", AsyncMock(side_effect=fake_get)):
        async with await _client() as ac:
            resp = await ac.get("/api/settings/ai/models")
    assert resp.status_code == 200
    assert resp.json()["models"] == []
    assert "error" in resp.json()


@pytest.mark.asyncio
async def test_ai_models_lists_from_gateway():
    async def fake_get(_db, _cat, key):
        return {"base_url": "http://gw", "api_key": "K"}.get(key)
    with patch("app.routers.settings.get_setting", AsyncMock(side_effect=fake_get)), \
         patch("app.routers.settings.llm_client.list_models",
               AsyncMock(return_value=["gemini/a"])):
        async with await _client() as ac:
            resp = await ac.get("/api/settings/ai/models")
    assert resp.json()["models"] == ["gemini/a"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_settings_ai.py -q`
Expected: FAIL (404 / Attribute 등 — 엔드포인트 없음)

- [ ] **Step 3: 구현 — import + 모델 + 라우트 추가**

`app/routers/settings.py` 상단 import에 추가:

```python
from app.services.ai import llm_client
```

`TelegramIn` 클래스 아래에 모델 추가:

```python
class AiIn(BaseModel):
    base_url: str | None = None
    api_key: str | None = None      # 빈/None이면 기존 키 유지
    model: str | None = None
    prompt: str | None = None
    enabled: bool | None = None
```

`@router.get("/telegram")` ~ `put_telegram` 블록 **뒤, 제너릭 `@router.get("/{category}/{key}")` 앞**에 AI 라우트 추가:

```python
_AI = "ai_gateway"


@router.get("/ai")
async def get_ai(db: AsyncSession = Depends(get_db)):
    return {
        "base_url": await get_setting(db, _AI, "base_url") or "",
        "api_key_set": bool(await get_setting(db, _AI, "api_key")),
        "model": await get_setting(db, _AI, "model") or "",
        "prompt": await get_setting(db, _AI, "prompt") or "",
        "enabled": (await get_setting(db, _AI, "enabled") or "false").lower() == "true",
    }


@router.get("/ai/models")
async def get_ai_models(db: AsyncSession = Depends(get_db)):
    base_url = await get_setting(db, _AI, "base_url")
    api_key = await get_setting(db, _AI, "api_key")
    if not base_url:
        return {"models": [], "error": "base_url이 설정되지 않았습니다."}
    try:
        return {"models": await llm_client.list_models(base_url, api_key or "")}
    except llm_client.LiteLLMError as e:
        return {"models": [], "error": str(e)}


@router.put("/ai")
async def put_ai(body: AiIn, db: AsyncSession = Depends(get_db)):
    if body.base_url is not None:
        await set_setting(db, _AI, "base_url", body.base_url, is_secret=False)
    if body.api_key:
        await set_setting(db, _AI, "api_key", body.api_key, is_secret=True)
    if body.model is not None:
        await set_setting(db, _AI, "model", body.model, is_secret=False)
    if body.prompt is not None:
        await set_setting(db, _AI, "prompt", body.prompt, is_secret=False)
    if body.enabled is not None:
        await set_setting(db, _AI, "enabled", "true" if body.enabled else "false", is_secret=False)
    return {"status": "ok"}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_settings_ai.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add app/routers/settings.py tests/test_settings_ai.py
git commit -m "feat(api): /api/settings/ai (get/put) + /ai/models gateway listing

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 차트 라우터 — analyze + send-telegram 통합 (`app/routers/charts.py`)

**Files:**
- Modify: `app/routers/charts.py`
- Test: `tests/test_charts_analyze.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_charts_analyze.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.ai import chart_analyzer
from app.services.ai.llm_client import LiteLLMError


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _asset():
    a = MagicMock()
    a.ticker, a.name, a.market, a.currency = "005930", "삼성전자", "KR", "KRW"
    return a


@pytest.mark.asyncio
async def test_analyze_returns_text():
    with patch("app.routers.charts._build_png", AsyncMock(return_value=b"\x89PNG")), \
         patch("app.routers.charts.chart_analyzer.analyze",
               AsyncMock(return_value=["<b>요약</b>", "두번째"])), \
         patch("app.db.AsyncSession.get", AsyncMock(return_value=_asset())):
        async with await _client() as ac:
            resp = await ac.post("/api/charts/1/analyze")
    assert resp.status_code == 200
    assert resp.json()["analysis"] == "<b>요약</b>\n\n두번째"


@pytest.mark.asyncio
async def test_analyze_disabled_returns_409():
    with patch("app.routers.charts._build_png", AsyncMock(return_value=b"\x89PNG")), \
         patch("app.routers.charts.chart_analyzer.analyze",
               AsyncMock(side_effect=chart_analyzer.AnalysisDisabled("off"))), \
         patch("app.db.AsyncSession.get", AsyncMock(return_value=_asset())):
        async with await _client() as ac:
            resp = await ac.post("/api/charts/1/analyze")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_analyze_gateway_error_returns_502():
    with patch("app.routers.charts._build_png", AsyncMock(return_value=b"\x89PNG")), \
         patch("app.routers.charts.chart_analyzer.analyze",
               AsyncMock(side_effect=LiteLLMError("boom"))), \
         patch("app.db.AsyncSession.get", AsyncMock(return_value=_asset())):
        async with await _client() as ac:
            resp = await ac.post("/api/charts/1/analyze")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_send_telegram_best_effort_when_ai_disabled():
    quote = MagicMock(price=70000)
    with patch("app.routers.charts._build_png", AsyncMock(return_value=b"\x89PNG")), \
         patch("app.routers.charts.get_quote", AsyncMock(return_value=quote)), \
         patch("app.routers.charts.telegram_service.send_photo", AsyncMock(return_value=True)), \
         patch("app.routers.charts.chart_analyzer.analyze",
               AsyncMock(side_effect=chart_analyzer.AnalysisDisabled("off"))), \
         patch("app.db.AsyncSession.get", AsyncMock(return_value=_asset())):
        async with await _client() as ac:
            resp = await ac.post("/api/charts/1/send-telegram")
    body = resp.json()
    assert resp.status_code == 200
    assert body["sent"] == 2
    assert body["analysis_sent"] is False


@pytest.mark.asyncio
async def test_send_telegram_sends_analysis_when_enabled():
    quote = MagicMock(price=70000)
    with patch("app.routers.charts._build_png", AsyncMock(return_value=b"\x89PNG")), \
         patch("app.routers.charts.get_quote", AsyncMock(return_value=quote)), \
         patch("app.routers.charts.telegram_service.send_photo", AsyncMock(return_value=True)), \
         patch("app.routers.charts.telegram_service.send_message", AsyncMock(return_value=True)) as sm, \
         patch("app.routers.charts.chart_analyzer.analyze",
               AsyncMock(return_value=["<b>분석</b>"])), \
         patch("app.db.AsyncSession.get", AsyncMock(return_value=_asset())):
        async with await _client() as ac:
            resp = await ac.post("/api/charts/1/send-telegram")
    assert resp.json()["analysis_sent"] is True
    sm.assert_awaited_once()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_charts_analyze.py -q`
Expected: FAIL (analyze 404, analysis_sent KeyError 등)

- [ ] **Step 3: 구현**

`app/routers/charts.py` 상단 import에 추가:

```python
import logging
from app.services.ai import chart_analyzer
```

`chart` GET 라우트 아래, `send_telegram` 위에 analyze 추가:

```python
@router.post("/{asset_id}/analyze")
async def analyze(asset_id: int, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    images = [(await _build_png(db, asset_id, p), "image/png") for p in ("daily", "weekly")]
    try:
        parts = await chart_analyzer.analyze(db, images, asset.ticker, asset.name, asset.market)
    except (chart_analyzer.AnalysisDisabled, chart_analyzer.AnalysisNotConfigured) as e:
        raise HTTPException(409, str(e))
    except chart_analyzer.llm_client.LiteLLMError as e:
        raise HTTPException(502, str(e))
    return {"analysis": "\n\n".join(parts)}
```

`send_telegram`를 아래로 교체(차트는 기존대로 발송하되 PNG를 재사용해 AI 분석 best-effort 추가):

```python
@router.post("/{asset_id}/send-telegram")
async def send_telegram(asset_id: int, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    quote = await get_quote(asset)
    caption = f"<b>{asset.name}</b> ({asset.ticker}·{asset.market})\n현재가: {quote.price:,} {asset.currency}"
    images: list[tuple[bytes, str]] = []
    sent = 0
    try:
        for i, period in enumerate(("daily", "weekly")):
            if i > 0:
                await asyncio.sleep(1)   # 연속 사진 rate limit(429) 회피
            png = await _build_png(db, asset_id, period)
            images.append((png, "image/png"))
            cap = f"{caption}\n[{period.upper()}]"
            if await telegram_service.send_photo(db, png, cap):
                sent += 1
    except telegram_service.TelegramNotConfigured as e:
        raise HTTPException(409, str(e))

    analysis_sent = False
    try:
        parts = await chart_analyzer.analyze(db, images, asset.ticker, asset.name, asset.market)
        for i, part in enumerate(parts):
            if i > 0:
                await asyncio.sleep(1)
            await telegram_service.send_message(db, part)
        analysis_sent = bool(parts)
    except (chart_analyzer.AnalysisDisabled, chart_analyzer.AnalysisNotConfigured):
        pass   # AI 미설정/비활성 → 차트만 발송
    except Exception as e:   # noqa: BLE001 — AI 실패가 차트 발송을 막지 않도록 best-effort
        logging.getLogger(__name__).warning("AI 분석 발송 실패(차트는 발송됨): %s", e)

    return {"sent": sent, "ok": sent > 0, "analysis_sent": analysis_sent}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_charts_analyze.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add app/routers/charts.py tests/test_charts_analyze.py
git commit -m "feat(api): chart analyze endpoint + AI analysis in send-telegram (best-effort)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 프론트엔드 — api + 설정 AI 섹션 + 차트 AI 버튼

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/pages/Settings.tsx`
- Modify: `frontend/src/pages/Charts.tsx`

- [ ] **Step 1: api.ts에 함수 추가**

`frontend/src/api.ts`의 `saveTelegram` 줄 뒤(객체 닫는 `};` 직전)에 추가:

```typescript
  getAi: () => j<{ base_url: string; api_key_set: boolean; model: string; prompt: string; enabled: boolean }>("/api/settings/ai"),
  saveAi: (a: { base_url?: string; api_key?: string; model?: string; prompt?: string; enabled?: boolean }) =>
    j("/api/settings/ai", { method: "PUT", body: JSON.stringify(a) }),
  listAiModels: () => j<{ models: string[]; error?: string }>("/api/settings/ai/models"),
  analyzeChart: (id: number) => j<{ analysis: string }>(`/api/charts/${id}/analyze`, { method: "POST" }),
```

- [ ] **Step 2: Settings.tsx 전체 교체(AI 섹션 추가)**

`frontend/src/pages/Settings.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api } from "../api";

export default function Settings() {
  // 텔레그램
  const [chatId, setChatId] = useState("");
  const [token, setToken] = useState("");
  const [tokenSet, setTokenSet] = useState(false);
  const [tgMsg, setTgMsg] = useState("");

  // AI
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiKeySet, setApiKeySet] = useState(false);
  const [model, setModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [prompt, setPrompt] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [aiMsg, setAiMsg] = useState("");

  const load = async () => {
    const t = await api.getTelegram();
    setChatId(t.chat_id); setTokenSet(t.bot_token_set); setToken("");
    const a = await api.getAi();
    setBaseUrl(a.base_url); setApiKeySet(a.api_key_set); setApiKey("");
    setModel(a.model); setPrompt(a.prompt); setEnabled(a.enabled);
  };
  useEffect(() => { load(); }, []);

  const saveTg = async () => {
    setTgMsg("저장 중…");
    const payload: any = { chat_id: chatId };
    if (token) payload.bot_token = token;
    await api.saveTelegram(payload);
    setTgMsg("저장됨"); await load();
  };

  const saveAi = async () => {
    setAiMsg("저장 중…");
    const payload: any = { base_url: baseUrl, model, prompt, enabled };
    if (apiKey) payload.api_key = apiKey;
    await api.saveAi(payload);
    setAiMsg("저장됨"); await load();
  };

  const refreshModels = async () => {
    setAiMsg("모델 조회 중…");
    try {
      const r = await api.listAiModels();
      setModels(r.models);
      setAiMsg(r.error ? `조회 실패: ${r.error}` : `${r.models.length}개 모델`);
    } catch (e: any) { setAiMsg("조회 실패: " + e.message); }
  };

  return (
    <div className="p-6 space-y-6 max-w-xl">
      <h1 className="text-xl font-bold">설정</h1>

      <section className="space-y-2">
        <h2 className="font-semibold text-gray-700">텔레그램</h2>
        <div className="flex gap-2 items-center">
          <label className="w-28 text-sm">봇 토큰</label>
          <input className="border rounded px-2 py-1 flex-1" type="password"
            placeholder={tokenSet ? "설정됨 (변경 시에만 입력)" : "봇 토큰 입력"}
            value={token} onChange={(e) => setToken(e.target.value)} />
        </div>
        <div className="flex gap-2 items-center">
          <label className="w-28 text-sm">chat_id</label>
          <input className="border rounded px-2 py-1 flex-1" placeholder="chat_id"
            value={chatId} onChange={(e) => setChatId(e.target.value)} />
        </div>
        <button onClick={saveTg} className="px-3 py-1 rounded bg-blue-600 text-white">저장</button>
        {tgMsg && <span className="text-sm text-gray-600 ml-2">{tgMsg}</span>}
      </section>

      <section className="space-y-2">
        <h2 className="font-semibold text-gray-700">AI 분석</h2>
        <div className="flex gap-2 items-center">
          <label className="w-28 text-sm">게이트웨이 URL</label>
          <input className="border rounded px-2 py-1 flex-1" placeholder="http://gateway:4000"
            value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
        </div>
        <div className="flex gap-2 items-center">
          <label className="w-28 text-sm">API 키</label>
          <input className="border rounded px-2 py-1 flex-1" type="password"
            placeholder={apiKeySet ? "설정됨 (변경 시에만 입력)" : "API 키 입력"}
            value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        </div>
        <div className="flex gap-2 items-center">
          <label className="w-28 text-sm">모델</label>
          {models.length > 0 ? (
            <select className="border rounded px-2 py-1 flex-1" value={model}
              onChange={(e) => setModel(e.target.value)}>
              {!models.includes(model) && model && <option value={model}>{model}</option>}
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          ) : (
            <input className="border rounded px-2 py-1 flex-1" placeholder="gemini/gemini-2.5-flash"
              value={model} onChange={(e) => setModel(e.target.value)} />
          )}
          <button onClick={refreshModels} className="px-2 py-1 rounded bg-gray-700 text-white text-sm whitespace-nowrap">모델 새로고침</button>
        </div>
        <div>
          <label className="text-sm block mb-1">프롬프트 (비우면 기본 프롬프트 사용)</label>
          <textarea className="border rounded px-2 py-1 w-full h-40 text-sm font-mono"
            value={prompt} onChange={(e) => setPrompt(e.target.value)} />
        </div>
        <label className="flex gap-2 items-center text-sm">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          AI 분석 사용 (텔레그램 발송 시 분석 코멘트 동반)
        </label>
        <button onClick={saveAi} className="px-3 py-1 rounded bg-blue-600 text-white">저장</button>
        {aiMsg && <span className="text-sm text-gray-600 ml-2">{aiMsg}</span>}
      </section>
    </div>
  );
}
```

- [ ] **Step 3: Charts.tsx 전체 교체(AI 분석 버튼 + 패널)**

`frontend/src/pages/Charts.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api } from "../api";

export default function Charts() {
  const [assets, setAssets] = useState<any[]>([]);
  const [assetId, setAssetId] = useState<number | null>(null);
  const [nonce, setNonce] = useState(() => Date.now());
  const [msg, setMsg] = useState("");
  const [analysis, setAnalysis] = useState("");
  const [analyzing, setAnalyzing] = useState(false);

  useEffect(() => { api.listAssets().then((a) => { setAssets(a); if (a[0]) setAssetId(a[0].asset_id); }); }, []);

  const send = async () => {
    if (!assetId) return;
    setMsg("발송 중…");
    try {
      const r: any = await api.sendChartTelegram(assetId);
      const extra = r.analysis_sent ? " + AI 분석" : "";
      setMsg(r.ok ? `텔레그램 발송 완료 (${r.sent}장${extra})` : "발송 실패");
    } catch (e: any) { setMsg("발송 실패: " + e.message); }
  };

  const analyze = async () => {
    if (!assetId) return;
    setAnalyzing(true); setAnalysis(""); setMsg("");
    try {
      const r = await api.analyzeChart(assetId);
      setAnalysis(r.analysis);
    } catch (e: any) { setAnalysis("분석 실패: " + e.message); }
    finally { setAnalyzing(false); }
  };

  const src = (period: "daily" | "weekly") =>
    assetId ? `${api.chartUrl(assetId, period)}&n=${nonce}` : "";

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <h1 className="text-xl font-bold">차트</h1>
        <select className="border rounded px-2 py-1" value={assetId ?? ""}
          onChange={(e) => { setAssetId(Number(e.target.value)); setMsg(""); setAnalysis(""); }}>
          {assets.map((a) => <option key={a.asset_id} value={a.asset_id}>{a.name} ({a.ticker}·{a.market})</option>)}
        </select>
        <button onClick={() => setNonce((n) => n + 1)} className="px-3 py-1 rounded bg-gray-800 text-white">새로고침</button>
        <button onClick={analyze} disabled={analyzing} className="px-3 py-1 rounded bg-emerald-600 text-white disabled:opacity-50">
          {analyzing ? "분석 중…" : "AI 분석"}
        </button>
        <button onClick={send} className="px-3 py-1 rounded bg-blue-600 text-white">텔레그램 발송</button>
        {msg && <span className="text-sm text-gray-600">{msg}</span>}
      </div>

      {analysis && (
        <div className="border rounded p-3 bg-gray-50 whitespace-pre-wrap text-sm leading-relaxed max-w-3xl">
          {analysis}
        </div>
      )}

      {assetId && (
        <div className="space-y-6">
          <div>
            <h2 className="font-semibold mb-1">일봉</h2>
            <img src={src("daily")} alt="daily chart" className="max-w-full border rounded"
              onError={(e) => ((e.target as HTMLImageElement).alt = "차트를 가져올 수 없습니다(수동/이력없음 자산일 수 있음)")} />
          </div>
          <div>
            <h2 className="font-semibold mb-1">주봉</h2>
            <img src={src("weekly")} alt="weekly chart" className="max-w-full border rounded"
              onError={(e) => ((e.target as HTMLImageElement).alt = "차트를 가져올 수 없습니다(수동/이력없음 자산일 수 있음)")} />
          </div>
        </div>
      )}
    </div>
  );
}
```

> 참고: 분석 텍스트에는 `<b>` 등 텔레그램 HTML 태그가 섞일 수 있다. `whitespace-pre-wrap` 텍스트 노드로 렌더하므로 XSS 위험 없이 태그가 평문으로 보인다(가독성 허용 범위). 후속에서 태그 제거/렌더 개선 가능.

- [ ] **Step 4: 빌드 확인**

Run: `cd frontend && npm run build`
Expected: 빌드 성공(에러 0)

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/api.ts frontend/src/pages/Settings.tsx frontend/src/pages/Charts.tsx
git commit -m "feat(frontend): AI settings section + chart AI analysis button

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: 전체 검증 + 로드맵 갱신

**Files:**
- Modify: `docs/superpowers/ROADMAP.md`

- [ ] **Step 1: 전체 단위 테스트**

Run:
```bash
SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q
```
Expected: 기존 41 + 신규(7+9+4+5=25) = **66 passed** (DB 미설정 시 일부 skip)

- [ ] **Step 2: 프론트 빌드**

Run: `cd frontend && npm run build`
Expected: 성공

- [ ] **Step 3: (선택) 실게이트웨이 스모크**

설정 페이지에서 base_url/api_key/model 입력·enabled 체크 후, 차트 화면에서 실 종목(005930) "AI 분석" 클릭 → 한국어 분석 텍스트 표시 확인. "텔레그램 발송" → 차트 2장 + 분석 메시지 도착 확인. (게이트웨이 미보유면 생략.)

- [ ] **Step 4: ROADMAP의 "2c" 섹션 갱신**

`docs/superpowers/ROADMAP.md`의 `### 2c: AI 차트 분석 — **미착수**` 블록을 다음으로 교체:

```markdown
### 2c: AI 차트 분석 — **구현 완료**
- spec: `docs/superpowers/specs/2026-06-15-ai-chart-analysis-design.md`
- plan: `docs/superpowers/plans/2026-06-15-ai-chart-analysis.md`
- 내용: 신규 `app/services/ai/`(llm_client=httpx Gemini native passthrough 비전, chart_analyzer=프롬프트·md→텔레그램 HTML·길이분할·설정게이팅). 설정 `ai_gateway` 카테고리(base_url/api_key(secret)/model/prompt/enabled). `GET/PUT /api/settings/ai`·`GET /api/settings/ai/models`. `POST /api/charts/{id}/analyze`(미리보기), `send-telegram`에 AI 분석 best-effort 통합(차트+분석 동반 발송). 프론트: 설정 AI 섹션(모델 드롭다운), 차트 "AI 분석" 버튼.
- 상태: 단위테스트 66 passed(신규 25), 빌드 통과. [실게이트웨이 스모크 결과 기입]
- 비고: per-asset 프롬프트·temperature UI·OpenAI호환 경로·결과 DB저장은 YAGNI로 제외.
```

- [ ] **Step 5: 커밋**

```bash
git add docs/superpowers/ROADMAP.md
git commit -m "docs: mark 2c (AI chart analysis) complete

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review 결과

- **Spec 커버리지:** llm_client(T1)·chart_analyzer(T2)·settings AI 엔드포인트(T3)·charts analyze+send 통합(T4)·프론트(T5)·검증/로드맵(T6) — spec의 모든 섹션 대응. 라우트 순서 주의(/ai/models vs 제너릭)도 T3에 명시.
- **플레이스홀더:** 코드/명령/기대출력 모두 구체값. (스모크 결과·게이트웨이 미보유 시 생략은 의도된 런타임 값.)
- **타입 일관성:** `analyze_images`/`list_models` 시그니처가 T1 정의와 T2·T3 호출에서 일치. `chart_analyzer.analyze`는 `list[str]` 반환 → charts.py에서 `"\n\n".join`/순차 send_message로 일관 사용. `AnalysisDisabled`/`AnalysisNotConfigured`/`LiteLLMError` 예외명 T2~T4 동일. 설정 키(base_url/api_key/model/prompt/enabled)·카테고리(`ai_gateway`) 전 태스크 일치.
