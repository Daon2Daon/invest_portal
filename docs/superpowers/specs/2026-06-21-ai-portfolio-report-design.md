# 3단계 B: AI 포트폴리오 리포트 — 설계 (spec)

작성일: 2026-06-21
선행: 3단계 A(일별 자산추세 스냅샷, 완료) — 스냅샷 추세 데이터를 입력으로 활용.

## 1. 목적

보유 포트폴리오를 LLM이 분석해 **종합 리포트**(진단 + 추세 리뷰 + 방향 제안)를 생성한다.
하나의 리포트가 다음 세 가지에 답한다.

1. **진단(스냅샷)**: 지금 내 포트폴리오 상태 — 자산군 편중·집중 위험·손익 현황.
2. **추세·성과 리뷰**: 최근 내 자산이 어떻게 변했나(3단계 A 스냅샷 추세 활용).
3. **방향 제안(비지시적)**: 사실 환기 + 행동 방향. "무엇을 몇 % 사라/팔라"는 구체 매매 지시는 회피. 하단에 "참고용" 디스클레이머 1줄.

## 2. 핵심 결정 요약

| 항목 | 결정 |
|------|------|
| 리포트 성격 | 종합(진단+추세+제안) |
| 트리거/전달 | 수동(온디맨드) + 자동 스케줄 + 텔레그램 |
| 이력 보관 | 저장(신규 `ai_reports` 테이블), 리포트 페이지에서 과거 조회 |
| 입력 데이터 | 린(포트폴리오 구성·summary·스냅샷 추세) + 종목별 최근 1주/1달 수익률 |
| 제안 수위 | 방향 제안(비지시적), 구체 매매 지시 회피 |
| 데이터→LLM | 마크다운 텍스트 블록 주입 |
| 신규 메뉴 | "리포트" (네비에 추가) |

## 3. 전체 구조 & 데이터 흐름

```
[데이터 수집]                    [생성]                  [저장/전달]
get_portfolio() ─┐
trend(snapshot) ─┼─→ report_data ─→ report_generator ─→ ai_reports 테이블
종목별 수익률    ─┘   (md 블록)      (프롬프트+LLM 텍스트)      │
(history/종목)                                                ├─→ 화면(리포트 페이지)
                                                             └─→ 텔레그램(md→HTML)
```

신규 서비스 디렉터리 `app/services/ai_report/`:

- **`report_data.py`** — `get_portfolio()` 결과 + 스냅샷 추세 + 종목별 1주/1달 수익률을 모아
  **마크다운 입력 블록**으로 구성. 변환 로직은 순수 함수 위주(테스트 용이).
  - 종목 수익률: history provider를 종목당 1회 호출(차트와 동일 패턴).
  - manual·무이력 자산: "(이력 없음)" 폴백, 전체 생성은 계속.
- **`report_generator.py`** — 입력 블록 + 프롬프트 → `llm_client` 텍스트 호출 → 마크다운 리포트.
  설정 게이팅(`ReportNotConfigured`/`ReportDisabled`), 2c `chart_analyzer` 패턴 차용. `DEFAULT_PROMPT` 보유.
- **`report_store.py`** — `ai_reports` 테이블 CRUD(생성/목록 최신순/단건/삭제).
- **`report_dispatch.py`** — 텔레그램 발송(기존 `telegram_service` + md→HTML 변환·길이분할 공용 헬퍼 재사용).

`llm_client.py`에 **텍스트 전용 함수 추가**(`generate_text` — Gemini generateContent, 텍스트 파트만).
현재는 비전(`analyze_images`)·모델목록(`list_models`)만 존재.

공용 헬퍼 추출: md→텔레그램 HTML 변환·길이분할이 현재 `chart_analyzer`에만 있음 →
작은 공용 모듈(`app/services/ai/telegram_md.py` 등)로 추출해 차트·리포트가 공유.
기존 차트 동작은 그대로 유지하는 순수 리팩터(회귀 없음).

## 4. 데이터 모델 — `ai_reports`

신규 테이블 1개. ensure_schema가 부팅 시 자동 생성(신규 테이블이라 ALTER 불필요, 3단계 A와 동일).

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | PK | |
| `created_at` | timestamptz | 생성 시각(KST 기록) |
| `title` | text | 예: "2026-06-21 포트폴리오 종합 리포트" |
| `content_md` | text | 생성된 마크다운 본문(진단+추세+제안+디스클레이머) |
| `model` | text | 생성에 쓴 모델명(재현·디버깅) |
| `trigger` | text | `manual` / `scheduled` |

- 입력 데이터 스냅샷은 저장하지 않음(YAGNI). 결과물은 `content_md`이고 그 시점 포트폴리오 상태는 본문에 서술됨.
- 목록은 `created_at` 내림차순. 보관 개수 제한·자동 삭제 없음(필요 시 후속).

## 5. API & 설정

### 5.1 리포트 라우트 `app/routers/reports.py` (`/api/reports`)

| 메서드 | 경로 | 동작 |
|--------|------|------|
| POST | `/api/reports` | 수동 생성 → 수집·LLM·저장 후 반환. `trigger=manual` |
| GET | `/api/reports` | 목록(최신순, 메타+본문 일부) |
| GET | `/api/reports/{id}` | 단건 전체 본문 |
| DELETE | `/api/reports/{id}` | 삭제 |
| POST | `/api/reports/{id}/send-telegram` | 텔레그램 발송(md→HTML, 길이분할) |

### 5.2 설정 — 신규 `ai_report` 카테고리

settings_manager 재사용(신규 마이그레이션 없음).

- 게이트웨이 **연결(base_url/api_key)은 기존 `ai_gateway`와 공유**(한 곳만 입력).
- 리포트 전용 키: `model`(텍스트 모델, 차트와 별도), `prompt`(편집 가능, `DEFAULT_PROMPT` 폴백), `enabled`(on/off).
- 라우트: `GET/PUT /api/settings/ai-report`.
- **별도 카테고리 이유**: 2c가 `ai_gateway`/`enabled`를 차트 분석에 쓰므로, 리포트가 같은 토글을
  건드리지 않도록 분리 → 차트와 리포트를 독립적으로 켜고 끔.

### 5.3 스케줄(자동 발송) — 기존 인프라 재사용, 신규 테이블 없음

- `schedules` 테이블에 `feature_type="ai_report"`, `target_id=0`(증시요약 `market_summary_*` 패턴과 동일 — 포트폴리오 전역).
- 스케줄러 디스패처에 `ai_report` 핸들러 등록 → 생성(`trigger=scheduled`) 후 텔레그램 발송.
- 휴장일 스킵 불필요(포트폴리오 진단은 매일/매주 의미 있음). 단순 send_time/days_of_week.
- 라우트: `GET/PUT /api/reports/schedule`(차트 `/api/charts/{id}/schedule` 패턴).

## 6. 프론트엔드

### 6.1 신규 메뉴 "리포트"

`AppShell` 네비에 추가(알림과 설정 사이), `/reports` 라우트 → `Reports.tsx`.

### 6.2 `Reports.tsx`

- 상단: **"리포트 생성" 버튼** — `POST /api/reports`(로딩 표시, 수 초 소요), 완료 후 목록 최상단 추가·선택.
- 목록: 제목 + 생성시각 + trigger 배지(manual/scheduled), 행 클릭 시 본문 표시, 삭제 버튼.
- 본문: 마크다운 렌더 + "텔레그램 발송" 버튼 + 하단 "참고용" 디스클레이머.
- 마크다운 렌더는 기존 차트 AI 패널 방식(`whitespace-pre-wrap`, XSS 안전) 재사용 — 신규 의존성 없음.
- 미구성·비활성 시 안내 문구(`ReportNotConfigured`/`ReportDisabled` → 친절한 메시지).

### 6.3 설정 페이지 "AI 리포트" 섹션

- 모델 드롭다운(+새로고침, `list_models` 재사용) · 프롬프트 편집(textarea, 기본값 폴백) · 활성화 토글.
- 자동 발송 스케줄 UI(시각/요일/활성화) — 차트 스케줄 섹션 패턴 재사용.

## 7. 에러 처리

- **설정 게이팅**: `ReportNotConfigured`(연결/모델 미설정)/`ReportDisabled`(off) → 라우트 명확한 4xx + 프론트 안내. 2c 동일.
- **LLM 실패**(`LiteLLMError`/타임아웃): 수동은 5xx 표면화 + 프론트 토스트. **스케줄은 best-effort** — tick 전체를 죽이지 않고 로깅.
- **종목 수익률 수집 실패**(history 에러·manual·무이력): 해당 종목만 "(이력 없음)" 폴백, 생성 계속.
- **빈 포트폴리오**(보유 0): 생성하되 "보유 자산 없음" 취지를 LLM에 전달(프롬프트가 처리).
- **텔레그램 미설정**: send-telegram 409(기존 차트 패턴).

## 8. 테스트 (invest_test 격리 스키마, 기존 관례)

- `report_data`: 마크다운 입력 블록 구성 순수 함수 단위테스트(포트폴리오 dict + 추세 + 종목수익률 → 블록, 폴백 포함).
- `report_generator`: 게이팅 분기(NotConfigured/Disabled), 프롬프트 빌드, llm_client mock.
- `report_store`: 생성/목록(최신순)/단건/삭제 DB 통합.
- `llm_client.generate_text`: Gemini 텍스트 응답 파싱(mock httpx).
- `reports` 라우트: POST/GET/GET{id}/DELETE/send-telegram(미설정 409).
- 스케줄 디스패처: `ai_report` 핸들러 `_is_due` 분기 + best-effort 실패 격리.
- `telegram_md` 공용 헬퍼: 추출 후 기존 차트 테스트 계속 통과(회귀 없음).
- **실게이트웨이/실텔레그램 스모크는 사용자 확인**(2c·2d 동일 — 설정 입력 필요).

## 9. 비목표 (YAGNI)

- 입력 데이터 스냅샷 DB 저장(재현성) — 본문에 상태 서술로 충분.
- 종목별 기술적 지표·뉴스 입력 — 차트 AI(2c)·3단계 C(위험신호) 영역과 중복.
- 구체 매매 지시(종목·수량) — 신뢰성·책임·근거 부족.
- 리포트 보관 개수 제한·자동 삭제, "지난주와 비교" 등 고급 활용.
- 텔레그램 외 채널, per-리포트 temperature UI.

## 10. 단계 내 위치

3단계(AI 리포트 + 투자저널 + 위험신호) 중 **B(AI 포트폴리오 리포트)**. A(스냅샷) 완료 위에 구축.
후속: C(위험신호·매수매도 도움), D(투자저널).
