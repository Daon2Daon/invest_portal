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

## 2.5단계: 보유/관심 IA + 자산 상세 허브 — **구현 완료 (main 병합됨, 2026-06-18, merge `035b7bf`)**
- spec: `docs/superpowers/specs/2026-06-18-holding-watchlist-ia-design.md`
- plan: `docs/superpowers/plans/2026-06-18-holding-watchlist-ia.md`
- 내용: 보유(포트폴리오)/관심종목을 **파생 분류**(holding lot 유무, 스키마 변경 0)로 구분. 백엔드 `held_asset_ids`·`get_asset_detail`(portfolio_service), `watchlist_service`, `GET /api/watchlist`, `GET /api/assets/{id}/detail`. 프론트 네비 재편(포트폴리오/관심종목/관리/설정), 신규 `Watchlist.tsx`, `Charts.tsx`→`AssetDetail.tsx`(자산별 기능 허브: 차트·AI분석·텔레그램·스케줄, 대시보드/관심종목 행 클릭 진입).
- 상태: 백엔드 93 테스트 통과(invest_test), 프론트 빌드 통과, 태스크별 spec+품질 2단계 리뷰 + 최종 리뷰 통과.
- 알려진 minor: `get_asset_detail`은 is_active 미필터(직접 URL로만 도달, 진입점 없음). 수동 브라우저 스모크는 사용자 확인.

## 가격 알림 — **구현 완료 (main 병합됨, 2026-06-18, merge `a7ba1b4`)**
- spec: `docs/superpowers/specs/2026-06-18-price-alerts-design.md`
- plan: `docs/superpowers/plans/2026-06-18-price-alerts.md`
- 내용: 자산별 `(basis, direction, value)` 모델 — ABSOLUTE(절대가)/PURCHASE_AVG(평균매입가±%)/WEEK52_HIGH/LOW(52주 고저점±%). 목표가=기준가×(1±value%), 1회성 발동→재무장. 5분 주기 + 시장 개장(거래일+장중)에만 평가→텔레그램. 신규 `PriceAlert` 모델, `services/alert/`(evaluator·basis(WEEK52 1h캐시)·message·alert_store·alert_dispatcher), `market/market_hours.py`(pandas_market_calendars), `/api/alerts` CRUD+rearm, 스케줄러 5분 `alert_tick` 잡(1분 tick과 별개), 자산 상세 허브 "가격 알림" 섹션.
- 상태: 백엔드 131 테스트 통과(invest_test), 프론트 빌드 통과, 그룹별 2단계 리뷰 + 최종 리뷰 "Ready".
- 결정: 반복 변동률(REFERENCE)·전역 알림 페이지·사용자 설정 주기·자동 재무장·텔레그램 외 채널은 비목표. 신규 의존성 `pandas_market_calendars`.
- 알려진 minor: manual 자산도 market 장중에만 평가; PUT /api/alerts/{id}는 UI 미사용; 퍼센트 value 상한 없음(≥100%면 영구 미발동); 수동 스모크는 사용자 확인.

## 매물대(Volume Profile) 복원 — **구현 완료 (main 병합됨, 2026-06-20, merge `66f442c`)**
- 내용: 2단계 차트에서 빠졌던 매물대를 복원. `chart_service._volume_profile`(가격대별 누적 거래량) + Panel1 `twiny` barh 오버레이(이평선/볼린저 뒤), `chart_analyzer.DEFAULT_PROMPT`에 매물대 해석 설명 추가(기본 프롬프트만).
- 상태: 백엔드 135 테스트 통과. 직접(서브에이전트 없이) TDD 구현.

## 알림 허브 + 디자인 시스템 통합 — **구현 완료 (2026-06-20)**
- spec: `docs/superpowers/specs/2026-06-20-alerts-hub-and-design-system-design.md`
- plan: `docs/superpowers/plans/2026-06-20-alerts-hub-and-design-system.md`
- 동기: 테스트 피드백 2건 — (1) 종목별로만 알림이 보여 전체 현황 파악 불가, (2) 디자인이 투박함.
- 내용:
  - **알림 허브**: `alert_store.list_all_alerts_view`(활성 자산 전체 알림 + 자산메타, 자산당 quote 1회 그룹화, `_alert_row` 헬퍼 공유) + `GET /api/alerts`의 `asset_id` 선택화(없으면 전체). 신규 `Alerts.tsx`(조회+생성+켜기끄기·삭제·재무장, 발동 시 "도달" 표시), 공용 `AlertForm`(허브 picker / 상세 fixed 모드, AssetDetail에서 추출 공유), 대시보드·관심종목 행에 알림 개수 배지. 생성/수정/삭제/재무장은 기존 엔드포인트 재사용.
  - **디자인 시스템**: `index.css` Vite 잔재 제거 + CSS 변수 토큰(라이트/다크) + 공용 클래스(`card/btn/btn-primary/input/badge`) + Tailwind 색상 매핑. 테마 토글(시스템 기본, localStorage 유지, `<html data-theme>`). 반응형 `AppShell`(≥lg 사이드바 / 미만 상단 탭바). 기존 5개 페이지 전부 토큰 재단장(빨강=상승/파랑=하락 유지, 다크모드 가독성 토큰화: ok/warn 패널 포함). 포인트색=보라(`--accent` 단일 토큰).
- 상태: 백엔드 **157 테스트 통과**(invest_test), 프론트 빌드 통과. 서브에이전트 주도 개발(태스크별 spec+품질 2단계 리뷰 + 최종 홀리스틱 리뷰). **수동 브라우저 스모크는 사용자 확인 대기**(테마 토글·반응형·알림 추가/관리 흐름).
- 비고(YAGNI 제외): 알림 발송 이력, 종목 검색 자동완성, 커스텀 테마색 UI, matplotlib 차트 다크모드, 허브에서의 값/방향 수정.

## 변동성(REFERENCE) 알림 — **구현 완료 (main 병합됨, 2026-06-20, merge `97caa8a`)**
- spec: `docs/superpowers/specs/2026-06-20-volatility-reference-alert-design.md`, plan: `docs/superpowers/plans/2026-06-20-volatility-reference-alert.md`
- 내용: my_assistant의 `PERCENT_CHANGE`(트레일링 반복 변동률) 이식. 기존 `PriceAlert`에 `REFERENCE` 기준 + `reference_price` 컬럼 추가. 양방향 `|변동률|≥X%` 발동(첫 tick lazy-init→미발동, 발동 시 텔레그램 발송 후 기준가를 현재가로 재설정해 계속 감시, `is_triggered` 불변). 5분 tick·장중 게이팅·텔레그램·알림 허브·배지 전부 재사용. `evaluator.ref_fired`(순수), `message.build_reference_message`, 디스패처 `is_reference` 분기, `_alert_row`에 reference_price, 라우터 `direction="BOTH"` 정규화(POST·PUT). 프론트: AlertForm "변동률 감시" 옵션(방향 드롭다운 숨김, 라벨 "변동 %"), 허브/AssetDetail 테이블 `±X%`·`기준가 ±X%`/`산정 중` 밴드 표시.
- 상태: 백엔드 **170 테스트 통과**(invest_test, 신규 13), 프론트 빌드·tsc 통과. 서브에이전트 주도 개발(태스크별 spec+품질 2단계 리뷰 + 최종 홀리스틱 리뷰). **브라우저 스모크 확인**(폼 방향숨김·밴드·산정중·재무장 없음·DB 원복).
- DB 마이그레이션: `ALTER TABLE invest.price_alerts ADD COLUMN IF NOT EXISTS reference_price NUMERIC`(dev DB 적용 완료). ensure_schema는 신규 DB 자동 생성.
- 비목표(YAGNI): 시간창 기반(전일종가/N분) 변동, 발송 이력/쿨다운, 절대금액 변동, REFERENCE 값 편집 UI.

## my-assistant 미이식 잔여 (비교검토 결과)
- ✅ 가격 알림(완료, 위), ✅ 거래일/장중 체크(가격알림의 market_hours로 충족), ✅ 매물대 패널(완료, 위), ✅ **변동성(REFERENCE) 알림**(완료, 바로 위 — PERCENT_CHANGE 이식).
- ✅ **증시 마감 요약 푸시** — **구현 완료 (main 병합됨, 2026-06-20, merge `79e641c`)**. spec/plan: `docs/superpowers/{specs,plans}/2026-06-20-market-summary-push*`. US/KR 시장별(지수+보유+관심 일/주/월·52주), `feature_type=market_summary_us/kr`+target_id=0로 기존 schedules 재사용, `market_hours.is_trading_day` 휴장 스킵, `services/market_summary/`+`routers/market_summary.py`+설정 섹션. 백엔드 155 테스트 통과.
- ⏳ 종목 검색 UX — 자산 등록 시 키워드 검색(KR=pykrx 리스트, US=제한적). 후순위.

## 3단계: AI 리포트 + 투자저널 + 위험신호 — **미착수**
- AI 포트폴리오 분석/리포트: ytdb의 분석 파이프라인·litellm 게이트웨이 패턴 참조. 설정은 `app_settings`의 `ai_gateway` 카테고리.
- 투자저널: 기존 테스트 DB `portfolio_plans`(context_date/summary/key_events/decisions/results/notes) 구조 재설계해 도입.
- 위험신호·매수매도 도움: 보유 자산의 기술적 지표·비중 편향 기반 알림.
- 일별 자산추세 스냅샷 테이블 추가(1단계에서 연기한 것).

## 후속: 포털 통합
- ytdb와 하나의 로그인 베이스 포털(invest/work/personal 메뉴)로 통합.
- 같은 PG 서버 공유. 1단계에서 ytdb의 다중그룹 제어평면은 제외했으므로, 통합 시 인증/메뉴 레이어를 별도 설계.
