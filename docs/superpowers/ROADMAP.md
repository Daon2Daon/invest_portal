# invest_portal 로드맵 (단계별 핸드오프)

다른 세션에서 이어받을 때 이 문서 → 해당 spec → plan 순으로 읽으면 됩니다.

## 1단계: 기반 + 포트폴리오 코어 — **진행 중 (계획 완료)**
- spec: `docs/superpowers/specs/2026-06-13-invest-portal-phase1-portfolio-core-design.md`
- plan: `docs/superpowers/plans/2026-06-13-invest-portal-phase1-portfolio-core.md`
- 내용: 앱 골격·DB 부트스트랩(ensure_schema)·멀티마켓 티커 해석(US/KR/JP/코인, ETF/ETN 분기, 채권 수동 모드)·포트폴리오 lot CRUD·KRW 환율변환·React 대시보드.

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
