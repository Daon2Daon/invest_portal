# 2c: AI 차트 분석 — 설계 (spec)

작성일: 2026-06-15
단계: 2단계(chartbot + 텔레그램)의 2c. 선행: 2a+2b(차트 생성 + 텔레그램 발송, main 병합 완료).
후속: 2d(스케줄 자동 발송)가 본 기능을 차트와 함께 자동 발송에 활용.

## 목적

차트 PNG(일봉+주봉)를 비전 LLM으로 분석해 기술적 코멘트(텍스트)를 생성한다.
사용자는 차트 화면에서 분석을 미리보고, 텔레그램으로 차트와 함께 발송할 수 있다.

## 확정된 결정

- **LLM 프로토콜:** ytdb `llm_client.py`와 동일한 **Gemini native passthrough**.
  `{base_url}/gemini/v1beta/models/{model}:generateContent` + `inlineData`(base64 PNG).
  `base_url`은 사용자가 직접 입력(비전 입력을 지원하는 LiteLLM 게이트웨이를 지정한다고 가정).
- **UX:** 차트 화면의 "AI 분석" 미리보기 버튼 + 기존 "텔레그램 발송"에 분석 통합.
- **설정:** base_url / api_key(secret) / model(게이트웨이 조회 드롭다운) / prompt / enabled.
- 무거운 의존성 추가 없음 — `httpx`만 사용(이미 의존성).

## 아키텍처

### 신규 모듈 `app/services/ai/`

기존 `notification`·`settings` 서비스와 동일한 결로 transport와 도메인을 분리한다.

**`app/services/ai/llm_client.py`** (transport)
- httpx 기반 경량 LiteLLM 클라이언트. ytdb/my-assistant `llm_client.py`에서 필요한 것만 발췌.
- `class LiteLLMError(RuntimeError)`
- `_normalize_base_url(raw)` — http(s) 접두 보정, trailing slash 제거.
- `_pick_text_from_gemini(payload)` — `candidates[0].content.parts[0].text` 안전 추출.
- `async analyze_images(base_url, api_key, model, images, prompt, temperature=None, max_output_tokens=None) -> str`
  - `model_id = model.split("/")[-1]`
  - `POST {base_url}/gemini/v1beta/models/{model_id}:generateContent?key={api_key}`
  - body: `{"contents":[{"role":"user","parts":[{inlineData...}*, {"text": prompt}]}], "generationConfig": {...}}`
  - 비200 → `LiteLLMError(상태코드+본문)`. 텍스트 없음 → `LiteLLMError`.
- `async list_models(base_url, api_key) -> list[str]`
  - `GET {base_url}/v1/models` (`Authorization: Bearer {api_key}` 헤더, key 있을 때만)
  - `data[].id` 목록 반환. 비200 → `LiteLLMError`.
- 호출마다 `httpx.AsyncClient(timeout=...)`를 컨텍스트로 생성(telegram_service와 동일 패턴). 클래스 상태/캐시 없음.

**`app/services/ai/chart_analyzer.py`** (도메인)
- `DEFAULT_PROMPT` — my-assistant `chart_analyzer.py`의 시니어 차티스트 프롬프트 이식(4패널 차트 구성 설명 포함).
- `_TELEGRAM_FORMAT_INSTRUCTION` — 텔레그램 HTML 출력 지시(append).
- `_md_to_telegram_html(text)` — 마크다운 → 텔레그램 호환 HTML(<b>,<i>,<code>,<pre>) 변환 + 미지원 태그 제거. my-assistant 로직 이식.
- `_split_message(text, limit=4000)` — 텔레그램 4096자 제한 대비 줄 단위 분할.
- `_build_prompt(user_prompt, ticker, name, market, chart_labels)` — 종목 메타·이미지 순서 prepend + 포맷 지시 append.
- `class AnalysisNotConfigured(Exception)` / `class AnalysisDisabled(Exception)`
- `async load_config(db) -> dict | None`
  - `settings_manager.get_setting(db, "ai_gateway", k)`로 base_url/api_key/model/prompt/enabled 로드.
  - enabled가 false면 `AnalysisDisabled`. base_url/api_key/model 중 누락 시 `AnalysisNotConfigured`.
  - prompt 미설정 시 `DEFAULT_PROMPT` 사용.
- `async analyze(db, images, ticker, name, market) -> list[str]`
  - config 로드 → 프롬프트 빌드 → `llm_client.analyze_images(...)` → `_md_to_telegram_html` → `_split_message` → 메시지 리스트 반환.
  - `images`: `[(png_bytes, "image/png"), ...]` 순서대로(일봉, 주봉).

### 설정 저장 — `app_settings` 카테고리 `ai_gateway`

기존 `settings_manager.get_setting/set_setting` 그대로 사용. 신규 테이블/마이그레이션 없음(AppSetting 기존 테이블).

| key | 저장 | 비고 |
|-----|------|------|
| `base_url` | plain | 게이트웨이 base URL |
| `api_key` | **secret**(Fernet) | 빈 입력 시 기존 유지 |
| `model` | plain | 예: `gemini/gemini-2.5-flash` |
| `prompt` | plain | 비면 DEFAULT_PROMPT |
| `enabled` | plain | `"true"`/`"false"` |

### API (라우터 변경)

**`app/routers/settings.py`** (추가)
- `GET /api/settings/ai` → `{base_url, api_key_set: bool, model, prompt, enabled: bool}` (api_key 원문 미노출).
- `PUT /api/settings/ai` (body: base_url?, api_key?, model?, prompt?, enabled?) — 텔레그램 PUT 패턴 동일(빈/None api_key는 기존 유지, 나머지는 전달된 값만 갱신).
- `GET /api/settings/ai/models` → `{models: [...], error?: str}`. 미설정/게이트웨이 실패 시 `{models: [], error}`(200, 프론트에서 안내).

**`app/routers/charts.py`** (추가/수정)
- `POST /api/charts/{id}/analyze` (신규)
  - `_build_png`로 일봉+주봉 생성 → `chart_analyzer.analyze` → `{analysis: str}`(메시지 리스트를 `\n\n`로 결합한 HTML 문자열, 미리보기용).
  - `AnalysisDisabled`/`AnalysisNotConfigured` → 409. `LiteLLMError` → 502. manual/이력없음 → 기존 422.
- `POST /api/charts/{id}/send-telegram` (수정)
  - 기존: 일봉·주봉 사진 발송.
  - 추가: AI enabled면 사진 발송 후 분석 메시지 생성→`telegram_service.send_message`로 발송(여러 조각이면 순차, 사이 sleep).
  - **AI 실패는 차트 발송을 막지 않음**(best-effort). 반환: `{sent, ok, analysis_sent: bool}`.
  - AI 미설정/비활성이면 분석 생략(차트만 발송, `analysis_sent: false`).

### 프론트엔드

**`frontend/src/pages/Settings.tsx`** — "AI 분석" 섹션 추가
- base_url(text), api_key(password, 설정됨 placeholder), model(드롭다운 + "모델 새로고침" 버튼 → `listAiModels`), prompt(textarea, 기본값 안내), enabled(체크박스), 저장 버튼.
- 모델 목록 비었거나 에러면 텍스트 입력 fallback 허용(드롭다운 옆 직접입력 또는 빈 목록 시 input).

**`frontend/src/pages/Charts.tsx`** — "AI 분석" 버튼 추가
- 클릭 → `analyzeChart(assetId)` → 로딩 표시 → 결과를 차트 아래 패널에 표시(HTML을 그대로 렌더하지 않고 텍스트/`whitespace-pre-wrap`로 안전 표시; 텔레그램 HTML 태그는 가독성 위해 간단 제거 또는 그대로 노출 중 택1 — 구현 시 텍스트 표시).
- 에러(409/502) → 안내 메시지. 기존 "텔레그램 발송" 버튼은 그대로(이제 AI 켜져있으면 분석 동반 발송).

**`frontend/src/api.ts`** — 추가
- `getAi()`, `saveAi(payload)`, `listAiModels()`, `analyzeChart(id)`.

## 데이터 흐름

```
[Charts: AI 분석 버튼]
  → POST /api/charts/{id}/analyze
    → _build_png(daily) + _build_png(weekly)
    → chart_analyzer.analyze(db, [(daily,png),(weekly,png)], ticker,name,market)
      → load_config(ai_gateway) → _build_prompt → llm_client.analyze_images(gemini native)
      → _md_to_telegram_html → _split_message
    → {analysis}
  → 화면 패널 표시

[Charts: 텔레그램 발송]
  → POST /api/charts/{id}/send-telegram
    → (기존) 일봉/주봉 send_photo
    → if AI enabled: chart_analyzer.analyze(...) → send_message(조각별)
    → {sent, ok, analysis_sent}
```

## 에러 처리

- AI 비활성/미설정: `analyze`는 409, `send-telegram`은 차트만 발송(`analysis_sent:false`).
- 게이트웨이 호출 실패(`LiteLLMError`): `analyze`는 502 + 메시지, `send-telegram`은 best-effort(차트 이미 발송, `analysis_sent:false`, 서버 로그 남김).
- manual/이력없음 자산: 기존 `_build_png`가 422.
- `/api/settings/ai/models`: 실패해도 200 + `{models:[], error}`로 프론트가 안내(설정 화면이 막히지 않게).

## 테스트

**단위(pytest)**
- `llm_client.analyze_images`: httpx mock으로 요청 body(parts에 inlineData+text, generationConfig) 구성 검증 + Gemini 응답 파싱.
- `llm_client.list_models`: `data[].id` 파싱, 비200 시 `LiteLLMError`.
- `_md_to_telegram_html`: 코드펜스/굵게/헤딩/미지원태그 변환.
- `_split_message`: 4000자 경계 분할.
- `chart_analyzer.load_config`: enabled false → `AnalysisDisabled`, 키 누락 → `AnalysisNotConfigured`, prompt 미설정 → DEFAULT_PROMPT.
- `GET/PUT /api/settings/ai`: api_key 마스킹(`api_key_set`), 빈 api_key PUT 시 기존 유지.

**스모크(실DB/실게이트웨이, 설정돼 있을 때만; 없으면 skip)**
- 실 종목(005930 등) analyze 호출 → 한국어 분석 텍스트 반환 확인.
- send-telegram → 차트 2장 + 분석 메시지 도착 확인.

빌드: `cd frontend && npm run build` 통과.

## YAGNI (이번 범위 제외)

- per-asset 프롬프트(전역 1개 prompt만).
- temperature/max_output_tokens UI 노출(코드 상수로 고정).
- OpenAI 호환 chat completions 경로(게이트웨이가 Gemini native 지원 가정).
- 모델 목록 캐싱(매번 조회, 사용 빈도 낮음).
- 분석 결과 DB 저장(2d/3단계에서 필요 시).

## 영향받는 파일 요약

- 신규: `app/services/ai/__init__.py`, `app/services/ai/llm_client.py`, `app/services/ai/chart_analyzer.py`
- 수정: `app/routers/settings.py`, `app/routers/charts.py`
- 신규 테스트: `tests/test_ai_llm_client.py`, `tests/test_chart_analyzer.py`, `tests/test_settings_ai.py`(기존 테스트 구조에 맞춤)
- 프론트: `frontend/src/pages/Settings.tsx`, `frontend/src/pages/Charts.tsx`, `frontend/src/api.ts`
- 의존성/마이그레이션: 없음.
