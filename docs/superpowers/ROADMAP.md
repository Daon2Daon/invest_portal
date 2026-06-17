# invest_portal 로드맵 (단계별 핸드오프)

다른 세션에서 이어받을 때 이 문서 → 해당 spec → plan 순으로 읽으면 됩니다.

## 1단계: 기반 + 포트폴리오 코어 — **구현 완료 (main 병합됨, 2026-06-13)**
- spec: `docs/superpowers/specs/2026-06-13-invest-portal-phase1-portfolio-core-design.md`
- plan: `docs/superpowers/plans/2026-06-13-invest-portal-phase1-portfolio-core.md`
- 내용: 앱 골격·DB 부트스트랩(ensure_schema)·멀티마켓 티커 해석(US/KR/JP/코인, ETF/ETN 분기, 채권 수동 모드)·포트폴리오 lot CRUD·KRW 환율변환(환차익 분리)·React 대시보드.
- 상태: **실DB 검증 완료** — 단위테스트 17 + DB 통합테스트 4 = **전체 21 passed**(invest_test 격리 스키마에서 실행), 앱 부팅 시 ensure_schema가 새 5개 테이블 생성, 실제 API 엔드투엔드 흐름(resolve AAPL→등록→FX→holding 자동 fx채움→portfolio KRW환산) 실데이터로 동작 확인. 프론트 빌드 통과.
- **DB 상태(2026-06-13 정리됨):**
  - DB 비밀번호: `mook123!` (느낌표 포함). `.env`의 `DATABASE_URL`에 반영됨(로컬, 미커밋).
  - 기존 `invest` 스키마의 9개 옛 테이블 + 시퀀스를 **`invest_legacy`로 이동**(rename은 admin 소유라 불가 → ai_agent가 테이블 단위 이동). 새 `invest`는 앱 5개 테이블만(비어 있음, 사용자 신규 입력 대기).
  - `invest_legacy.economist_claims`(134행)·experts·video_asset_mentions 보존됨. **`anthropic-skills:economist-claims` 스킬이 `invest.economist_claims`를 참조하므로, 사용자가 스킬을 `invest_legacy`로 수정 예정**(DB는 현 상태 유지).
  - 통합테스트 재실행: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q` (격리 스키마, 운영 invest 무손상).
  - 실행: 백엔드 `.venv/bin/uvicorn app.main:app`, 프론트 `cd frontend && npm run dev`(localhost:5173).
- 향후 폴리시(리뷰에서 minor로 분류, 미적용): manual_price_currency 환산 처리, 라우트 response_model 보강, holdings.asset_id 인덱스, CORS config화.
- Docker: 단일 컨테이너(FastAPI가 빌드된 React SPA를 /static/ui로 same-origin 서빙), `Dockerfile`·`docker-compose.yml`(로컬)·`portainer-stack.yml`(프로덕션)·`.dockerignore`. 외부 공유 DB 사용. 이미지 빌드+컨테이너 실행 검증 완료.

## 1.5단계: 현금 자산군 + 보유종목 등록 정비 — **구현 완료 (main 병합됨, 2026-06-14)**
- spec: `docs/superpowers/specs/2026-06-14-cash-and-holdings-refinements-design.md`
- plan: `docs/superpowers/plans/2026-06-14-cash-and-holdings-refinements.md`
- 내용: (1) 현금 자산군(`cash_balances` 테이블, /api/cash CRUD, 포트폴리오 총자산·비중 포함), (2) 보유종목 등록 통합(`POST /api/holdings/with-asset` = 자산 upsert+보유 한 번에, 단일 폼), (3) 매입날짜 선택 입력(nullable), (4) 환율 단순화(`purchase_fx_rate` 제거 — 원가도 현재환율로 환산, 환차익 미분리; 손익은 자산통화 기준).
- 상태: 단위테스트 20 passed/4 skipped, 프론트 빌드 통과, 실DB 엔드투엔드 검증(현금 비중 합 ~100%, with-asset 생성, 날짜 None). 최종 리뷰 Critical/Important 0건.
- DB 마이그레이션: 사용자 실데이터(005930·112610 보유 2건)가 있어 drop 대신 **ALTER in-place**(purchase_fx_rate 컬럼 제거 + purchase_date DROP NOT NULL)로 데이터 보존. `cash_balances`는 부팅 시 자동 생성.
- **UI 간소화(2026-06-14 추가, main `f6910c4`):** 자산등록·현금 페이지 제거 → 메뉴를 **대시보드·보유 2개**로 통합. 보유 화면에서 종목·현금 입력 + 보유/현금 목록 **인라인 수정**(자산명 표시). 죽은 createAsset/createHolding api 제거. 같은 티커 재입력 시 with-asset이 분할매수 처리. (이전 "현금 수정 폼 없음·asset_id만 표시" UX 항목 해결됨.)
- **참고:** pykrx 005930 현재가는 정상(사용자 확인). 별도 점검 불필요.
- **KR ETF 조회 수정(2026-06-14, main `6c447dc`):** pykrx 1.2.8의 ETF 엔드포인트(get_etf_ticker_list/ohlcv)가 현재 KRX API와 안 맞아 깨짐(KeyError '시장'/'isin') → KR ETF는 pykrx 실패 후 yfinance 폴백으로 처리. YFinanceProvider가 KR에 `.KS`→`.KQ` 접미사를 붙이도록 수정(통화 KRW)해 KR ETF/주식 모두 yfinance 폴백 가능. 즉 **KR 주식=pykrx, KR ETF=yfinance(.KS)** 로 동작. pykrx ETF 지원이 복구되면 _classify가 다시 ETF로 분기하나, yfinance 폴백이 안전망으로 유지됨.
- **남은 UX/기능 후보:** 수동가격(채권 등) 입력 UI 없음(manual-price 엔드포인트는 있음). 관심종목(watchlist) 메뉴는 2단계.

## 자산군 분류 + 자산군별 비중 — **구현 완료 (main 병합됨, 2026-06-14)**
- spec: `docs/superpowers/specs/2026-06-14-asset-class-classification-design.md`
- plan: `docs/superpowers/plans/2026-06-14-asset-class-classification.md`
- 내용: `assets.asset_class`(단일, 추천목록 주식/채권/현금성/원자재/가상자산/대체투자/기타 + 자유입력), asset_type→자산군 기본 매핑(`default_asset_class`), 등록 시 자동 채움 + 수정(`PUT /api/assets/{id}`), 대시보드 자산군별 비중 표(현금=현금성). 보유 폼/목록에서 자산군 입력·인라인 수정.
- 상태: 단위테스트 27 passed/4 skipped, 빌드 통과, 실DB 엔드투엔드(resolve 기본값→with-asset 저장→portfolio asset_class·allocation→PUT로 자산군 이동) 검증. 스모크에서 버그 1건(HoldingWithAssetCreate에 asset_class 누락 → with-asset 500) 발견·수정.
- DB 마이그레이션: `ALTER TABLE invest.assets ADD COLUMN IF NOT EXISTS asset_class TEXT` + 기존 8개 자산 asset_type 기준 backfill(완료). **주의**: ensure_schema는 create-only라 기존 DB는 이 ALTER가 필요(신규 DB는 모델에 컬럼이 있어 자동 생성). 현재 dev DB는 적용 완료.
- 참고: 같은 티커 재추가(분할매수)는 자산의 asset_class를 덮어쓰지 않음(분류 보존). 자산군 변경은 PUT으로.
- 후속 후보: 다중 태그, 자산군별 목표비중·리밸런싱, 파이차트 시각화.

## 2단계: chartbot + 텔레그램

### 2a+2b: 차트 생성 + 텔레그램 발송 — **구현 완료 (main 병합됨, 2026-06-14)**
- spec: `docs/superpowers/specs/2026-06-14-chart-generation-telegram-design.md`
- plan: `docs/superpowers/plans/2026-06-14-chart-generation-telegram.md`
- 내용: provider `history()` + data_source 디스패치(`history_service`), matplotlib 4패널 TA 차트(일봉/주봉 온더플라이 PNG, `chart_service`), `GET /api/charts/{id}` + "차트" 메뉴, 텔레그램 설정(봇토큰 Fernet, `app_settings.notification`)+`telegram_service`+`POST /api/charts/{id}/send-telegram`, "설정" 메뉴(텔레그램 섹션), Dockerfile `fonts-nanum`.
- 상태: 단위테스트 37 passed/4 skipped, 빌드 통과, 실DB 스모크(005930/112610 일봉·주봉 PNG 200, send-telegram 토큰미설정 409). 종합 리뷰 Critical/Important 0(딜리버리 신뢰성 fix 2건 반영: 사진 사이 sleep, 주봉 onError).
- KR ETF는 data_source=yfinance(.KS)라 history도 yfinance, KR 주식은 pykrx. manual 자산은 차트 불가(422).
- **노트(저위험, 미적용):** `registry.for_source`가 미지 data_source에 KeyError→500(앱 경로상 발생 불가, get_quote와 공유되는 기존 패턴). 차후 방어코드 추가 가능.
- 메뉴: 대시보드·보유·차트·설정.

### 2c: AI 차트 분석 — **구현 완료 (2026-06-15)**
- spec: `docs/superpowers/specs/2026-06-15-ai-chart-analysis-design.md`
- plan: `docs/superpowers/plans/2026-06-15-ai-chart-analysis.md`
- 내용: 신규 `app/services/ai/`(llm_client=httpx Gemini native passthrough 비전 + 모델목록, chart_analyzer=프롬프트빌드·md→텔레그램 HTML·길이분할·설정게이팅). 설정 `ai_gateway` 카테고리(base_url/api_key(secret)/model/prompt/enabled, settings_manager 재사용 — 신규 마이그레이션 없음). `GET/PUT /api/settings/ai`·`GET /api/settings/ai/models`(라우트 순서: 제너릭 `/{category}/{key}`보다 먼저). `POST /api/charts/{id}/analyze`(미리보기), `send-telegram`에 AI 분석 best-effort 통합(차트 PNG 재사용, AI 실패가 차트 발송을 막지 않음, `analysis_sent` 반환). 프론트: 설정 AI 섹션(모델 드롭다운+새로고침), 차트 "AI 분석" 버튼+패널(whitespace-pre-wrap, XSS 안전).
- 상태: 단위테스트 **65 passed**(신규 24: llm_client 6 + chart_analyzer 9 + settings_ai 4 + charts_analyze 5), 프론트 빌드 통과. 태스크별 spec/품질 2단계 리뷰 통과. **실게이트웨이 스모크 미실시(게이트웨이 설정 시 사용자 확인 필요).**
- 프로토콜: ytdb와 동일 Gemini native passthrough, base_url 직접 입력(비전 지원 게이트웨이 가정).
- 비고: per-asset 프롬프트·temperature UI·OpenAI호환 경로·결과 DB저장·모델목록 캐싱은 YAGNI로 제외. 잘린 LLM 출력의 미닫힘 코드펜스는 평문 노출(미용상, 후속 개선 가능).

### 2d: 스케줄 자동 발송 — **구현 완료 (2026-06-16)**
- spec: `docs/superpowers/specs/2026-06-16-scheduled-auto-send-design.md`
- plan: `docs/superpowers/plans/2026-06-16-scheduled-auto-send.md`
- 내용: 신규 `schedules` 테이블(범용: feature_type/target_id/send_time/days_of_week/enabled/last_run_date, ensure_schema 자동생성) + `app/services/scheduler/`(AsyncIOScheduler 메모리 잡스토어 + 1분 tick 디스패처 + `_is_due` 순수함수 + feature_type 핸들러 레지스트리). 발송 로직은 `chart_dispatch.send_chart_telegram`(라우트에서 추출)·`chart_builder.build_png`로 분리해 수동 발송/자동 발송이 공유. 스케줄 CRUD API(GET/PUT/DELETE `/api/charts/{id}/schedule`), main.py lifespan에 start/shutdown_scheduler. 프론트: 차트 페이지 "자동 발송 스케줄" 섹션(시각/요일/활성화).
- 결정: 종목당 1개 스케줄, 잡스토어=메모리(진실의 원천=DB 테이블), KST 고정, 미스된 실행은 그날 안 늦게라도 발송(자정 넘기면 폐기), 방해금지 로직 없음. 중앙 디스패처라 여러 발송 기능이 같은 테이블·tick을 공유(향후 확장점).
- 상태: 단위/통합테스트 **86 passed**(신규: schedule_store 4 + dispatcher 7 + charts_schedule 7 + 테이블 1), 프론트 빌드 통과. **실 스케줄 스모크는 사용자 확인 필요(가까운 시각 등록 후 발송 확인).**
- 비고: 종목당 복수 스케줄·PG 잡스토어·기능별 별도 테이블·자정 catch-up·발송 이력 로그는 YAGNI로 제외.

## 3단계: AI 리포트 + 투자저널 + 위험신호 — **미착수**

## 3단계: AI 리포트 + 투자저널 + 위험신호 — **미착수**
- AI 포트폴리오 분석/리포트: ytdb의 분석 파이프라인·litellm 게이트웨이 패턴 참조. 설정은 `app_settings`의 `ai_gateway` 카테고리.
- 투자저널: 기존 테스트 DB `portfolio_plans`(context_date/summary/key_events/decisions/results/notes) 구조 재설계해 도입.
- 위험신호·매수매도 도움: 보유 자산의 기술적 지표·비중 편향 기반 알림.
- 일별 자산추세 스냅샷 테이블 추가(1단계에서 연기한 것).

## 후속: 포털 통합
- ytdb와 하나의 로그인 베이스 포털(invest/work/personal 메뉴)로 통합.
- 같은 PG 서버 공유. 1단계에서 ytdb의 다중그룹 제어평면은 제외했으므로, 통합 시 인증/메뉴 레이어를 별도 설계.
