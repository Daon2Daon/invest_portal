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
- **남은 UX/기능 후보:** 수동가격(채권 등) 입력 UI 없음(manual-price 엔드포인트는 있음). 관심종목(watchlist) 메뉴는 2단계.

## 2단계: chartbot + 텔레그램 — **미착수**
시작 시 `superpowers:brainstorming`으로 새 spec 작성. 핵심:
- chartbot 포팅: my-assistant `app/services/bots/chart_bot.py`(4패널 캔들+RSI+MACD+거래량)·`chart_analyzer.py`(AI 해석)의 검증된 로직만 선별 참조해 새로 작성.
- 1단계에 둔 `PriceProvider.history(asset, start, end)` 인터페이스를 차트 OHLCV 소스로 재사용.
- 텔레그램 발송: ytdb `app/services/`의 텔레그램 패턴 참조. 설정은 `app_settings`의 `notification` 카테고리(봇 토큰은 Fernet secret).
- 스케줄 리포트: APScheduler 도입(ytdb 참조), 잡스토어는 메모리 또는 PG.

## 3단계: AI 리포트 + 투자저널 + 위험신호 — **미착수**
- AI 포트폴리오 분석/리포트: ytdb의 분석 파이프라인·litellm 게이트웨이 패턴 참조. 설정은 `app_settings`의 `ai_gateway` 카테고리.
- 투자저널: 기존 테스트 DB `portfolio_plans`(context_date/summary/key_events/decisions/results/notes) 구조 재설계해 도입.
- 위험신호·매수매도 도움: 보유 자산의 기술적 지표·비중 편향 기반 알림.
- 일별 자산추세 스냅샷 테이블 추가(1단계에서 연기한 것).

## 후속: 포털 통합
- ytdb와 하나의 로그인 베이스 포털(invest/work/personal 메뉴)로 통합.
- 같은 PG 서버 공유. 1단계에서 ytdb의 다중그룹 제어평면은 제외했으므로, 통합 시 인증/메뉴 레이어를 별도 설계.
