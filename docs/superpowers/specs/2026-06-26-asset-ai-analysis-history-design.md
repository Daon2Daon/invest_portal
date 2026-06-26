# 종목별 AI 분석 — 마크다운 렌더링 + 히스토리 저장 설계

**작성일:** 2026-06-26
**상태:** 설계 승인 대기

## 배경 / 문제

종목 상세 화면(`AssetDetail`)의 `AI 분석` 버튼은 차트 이미지(일봉/주봉)를 LLM에 보내 기술적 분석 텍스트를 받는다. 두 가지 문제가 있다.

1. **HTML이 글자 그대로 출력됨.** AI 분석은 원래 텔레그램 발송용으로 설계되어, 프롬프트가 LLM에게 텔레그램 HTML 태그(`<b>`, `<i>`, `<code>`, `<pre>`)로 출력하도록 강제한다(`chart_analyzer._TELEGRAM_FORMAT_INSTRUCTION`). 웹은 이 텍스트를 `whitespace-pre-wrap`로 순수 텍스트 표시(`AssetDetail.tsx:140`)하므로 태그가 그대로 노출된다. 프론트에는 마크다운/HTML 렌더러가 없다.
2. **분석 결과가 저장되지 않음.** `POST /api/charts/{id}/analyze`는 텍스트를 반환만 하고 영속화하지 않아, 화면을 새로고침하면 사라진다. 과거 분석과 현재를 비교할 수 없다.

기존 `AIReport`(`ai_reports` 테이블)는 **포트폴리오 단위 정기 리포트**용으로 `asset_id`가 없어 종목별 분석과 무관하다.

## 결정 사항 (brainstorming)

- **저장 방식:** 히스토리 누적, 단 **종목당 최신 N건(기본 20)만 보관**, 초과분 자동 삭제.
- **렌더링:** LLM이 **마크다운**으로 출력 → 저장은 마크다운 원문 → 웹은 마크다운 렌더, 텔레그램은 기존 `md_to_telegram_html` 변환 사용.
- **저장 트리거:** **분석 실행 시 자동 저장**(웹 버튼 + 텔레그램 스케줄/수동 발송 모두).
- **마크다운 렌더러:** `react-markdown` 추가.

## 아키텍처

### 1. 출력 형식 정규화 (HTML 문제의 근본 해결)

`app/services/ai/chart_analyzer.py`:

- `_TELEGRAM_FORMAT_INSTRUCTION`(HTML 태그 강제)을 마크다운 지향 `_FORMAT_INSTRUCTION`으로 교체한다. 내용: 개조식·불릿 위주, `**굵게**`/`*기울임*`, `#`~`###` 헤딩 사용, 분량 가이드 유지. HTML 태그 언급 제거.
- `_build_prompt`는 이 새 instruction을 append.
- **텔레그램 경로 영향 없음:** `chart_analyzer.analyze()`는 `analyze_raw()`(마크다운) → `telegram_md.md_to_telegram_html()` → `split_message()`로 변환한다. `md_to_telegram_html`는 이미 마크다운(`**bold**`, `# 헤딩`, 불릿, `` `code` ``)을 텔레그램 HTML로 변환하도록 설계되어 있어 그대로 동작하며 오히려 더 견고하다.
- **웹 경로:** 마크다운 원문을 그대로 렌더.

`analyze_raw`는 현재 model명을 반환하지 않는다. 저장 시 model이 필요하므로, `analyze_raw`가 `(text, model)` 튜플을 반환하도록 변경한다(또는 `load_config` 결과의 `model`을 호출부에서 재사용). **결정: `analyze_raw`가 `(text, model)` 반환.** 텔레그램 경로의 `analyze()`도 이에 맞춰 unpack.

### 2. 신규 모델 `app/models/asset_ai_analysis.py`

```python
class AssetAIAnalysis(Base):
    __tablename__ = "asset_ai_analyses"

    id: Mapped[int]            # PK
    asset_id: Mapped[int]      # FK -> assets.id, index=True
    content_md: Mapped[str]    # Text, 마크다운 원문
    model: Mapped[str]         # String, 사용 모델명, default ""
    trigger: Mapped[str]       # String, "manual" | "scheduled", default "manual"
    created_at: Mapped[datetime]  # DateTime(timezone=True), server_default=func.now()
```

- `app/models/__init__.py`에 export 추가.
- 부팅 시 `app/bootstrap.py`의 `Base.metadata.create_all`로 멱등 생성(기존 패턴, 마이그레이션 도구 없음).
- `asset_id`에 인덱스(종목별 조회·prune 효율).

### 3. 저장 모듈 `app/services/ai/analysis_store.py`

`report_store.py` 패턴을 따른다.

- `KEEP_DEFAULT = 20` 상수.
- `async def create_and_prune(db, asset_id, content_md, model, trigger, keep=KEEP_DEFAULT) -> AssetAIAnalysis`
  - row insert → commit → 같은 asset_id에서 `created_at`/`id` 최신순 정렬 후 `keep` 초과 행 삭제 → commit.
- `async def list_for_asset(db, asset_id, limit=KEEP_DEFAULT) -> list[AssetAIAnalysis]` — 최신순.
- `async def delete(db, analysis_id) -> bool` — 개별 삭제(선택 엔드포인트용).

### 4. 자동 저장 와이어링

**웹 — `app/routers/charts.py` `analyze` 엔드포인트:**
- `text, model = await chart_analyzer.analyze_raw(...)`
- `row = await analysis_store.create_and_prune(db, asset_id, text, model, trigger="manual")`
- 응답: `{"analysis": text, "id": row.id, "created_at": row.created_at}`.

**텔레그램 — `app/services/notification/chart_dispatch.py` `send_chart_telegram`:**
- 현재 `chart_analyzer.analyze()`를 호출(내부에서 `analyze_raw` 1회). 저장을 위해 마크다운 원문이 필요하므로 다음으로 리팩터:
  - `raw, model = await chart_analyzer.analyze_raw(db, images, ...)`
  - `await analysis_store.create_and_prune(db, asset.id, raw, model, trigger=trigger)` (best-effort, 실패해도 발송 진행)
  - `parts = telegram_md.split_message(telegram_md.md_to_telegram_html(raw))` 로 텔레그램 발송.
- `send_chart_telegram(db, asset, trigger="manual")` 시그니처에 `trigger` 추가. 스케줄러 핸들러는 `trigger="scheduled"`, 수동 발송 라우트는 `"manual"` 전달.
- 저장/분석 실패는 기존처럼 best-effort(차트 발송은 막지 않음). `AnalysisDisabled`/`NotConfigured` 시 저장도 건너뜀.

### 5. API (`app/routers/charts.py`)

- 기존 `POST /api/charts/{asset_id}/analyze` — 저장 추가(위 4).
- 신규 `GET /api/charts/{asset_id}/analyses?limit=20` → `[{id, content_md, model, trigger, created_at}]` 최신순.
- 신규 `DELETE /api/charts/analyses/{analysis_id}` → 개별 삭제(204 또는 `{ok}`).

### 6. 프론트엔드

**의존성:** `react-markdown` 추가(`frontend/package.json`).

**`frontend/src/api.ts`:**
- `analyzeChart` 응답 타입에 `id`, `created_at` 추가.
- `listAnalyses(assetId, limit?)`, `deleteAnalysis(id)` 추가.
- `AssetAnalysis` 타입(`id, content_md, model, trigger, created_at`).

**`frontend/src/pages/AssetDetail.tsx`:**
- 진입 시 `listAnalyses(assetId)`로 히스토리 로드.
- 최신 1건은 펼쳐서 `<ReactMarkdown>`으로 렌더(기존 `whitespace-pre-wrap` 순수 텍스트 박스 교체). 마크다운 타이포는 Tailwind 유틸로 최소 스타일.
- 이전 건들은 `created_at`(KST) 타임스탬프 리스트로 접어두고, 클릭 시 펼쳐 마크다운 렌더. (선택) 각 항목 삭제 버튼.
- `AI 분석` 버튼: 클릭 → analyze 호출 → 응답을 히스토리 맨 앞에 prepend(자동 저장됨). 별도 저장 버튼 없음.

## 데이터 흐름

```
[웹] AI분석 버튼 → POST /analyze
   → chart_analyzer.analyze_raw (마크다운, model)
   → analysis_store.create_and_prune(trigger=manual)   # N건 유지
   → 응답(analysis md) → react-markdown 렌더 + 히스토리 prepend

[텔레그램] 스케줄러/수동발송 → chart_dispatch.send_chart_telegram(trigger)
   → analyze_raw (마크다운, model)
   → analysis_store.create_and_prune(trigger)           # best-effort
   → md_to_telegram_html → split_message → 텔레그램 발송
```

## 에러 처리

- 웹 `analyze`: 기존 예외 매핑 유지(`AnalysisDisabled`/`NotConfigured`→409, `LiteLLMError`→502). 저장은 분석 성공 후이므로 분석 실패 시 저장 안 함.
- 텔레그램: 분석/저장 실패는 best-effort(차트는 발송). 기존 동작 보존.
- prune: 삭제 실패가 저장 자체를 롤백하지 않도록 분리(저장 commit 후 prune).

## 테스트

- `analysis_store`: 21건 저장 시 20건만 남고 가장 오래된 것 삭제. 종목 간 격리(asset A의 prune이 asset B 영향 없음).
- `charts.analyze`: 호출 후 row 1건 생성, 응답에 id/created_at 포함.
- `GET /analyses`: 최신순, limit 적용.
- `chart_analyzer`: 새 프롬프트로 `analyze_raw`가 마크다운 반환(HTML 태그 강제 instruction 부재) + `(text, model)` 형태.
- 회귀: `chart_dispatch`가 마크다운→텔레그램 HTML 변환 경로로 정상 발송(분석 1회만 호출).

## 범위 밖 (YAGNI)

- N값 사용자 설정 UI(상수 고정, 추후 settings 확장 가능).
- 분석 간 diff 시각화.
- 포트폴리오 `AIReport`와의 통합/공용 모델화.
