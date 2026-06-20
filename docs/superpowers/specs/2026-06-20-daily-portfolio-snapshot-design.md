# 일별 자산추세 스냅샷 — 설계 (3단계 A)

작성일: 2026-06-20

## 배경 / 목적

3단계(AI 리포트 + 투자저널 + 위험신호)의 첫 하위 시스템. 매일 포트폴리오의
총자산·원가·평가손익·현금과 자산군별 구성을 시계열로 적재해, 시간에 따른
**자산추세**를 볼 수 있게 한다. 추세 데이터는 빨리 시작할수록 의미가 커지므로
(시간이 지나야 쌓이는 데이터) 3단계 4개 하위 시스템 중 가장 먼저 구현한다.

현재 `get_portfolio()`는 총자산·자산군별 비중을 **매번 실시간 계산**할 뿐 시계열로
저장하지 않는다. 기존 `PriceSnapshot` 모델(자산별 일일 종가)이 존재하나 어디서도
사용되지 않으며, 이는 포트폴리오 레벨 추세와는 결이 다르다(이번 범위 밖, 미사용 유지).

## 범위 (3단계 A만)

- 매일 고정 시각 cron으로 포트폴리오 레벨 스냅샷 1행 적재.
- `GET /api/trend` 조회 API.
- 대시보드에 총자산 추세 라인차트(자체 SVG, 의존성 0).

비목표(YAGNI): 과거 백필, 자산군 스택차트, 스냅샷 시각 설정 UI, 발송/알림 연동,
종목별 추세, 기존 `PriceSnapshot` 활용/제거.

## 1. 데이터 모델 — `portfolio_snapshots` 신규 테이블

기존 미사용 `PriceSnapshot`(자산별 종가)와 별개의 **포트폴리오 레벨** 테이블.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | PK (int) | |
| `date` | Date, **unique** | 날짜당 1행(멱등 보장) |
| `total_value_krw` | Numeric | 총자산(종목 + 현금) |
| `total_cost_krw` | Numeric | 원가 합 |
| `total_pl_krw` | Numeric | 평가손익(종목 기준) |
| `total_cash_krw` | Numeric | 현금 |
| `allocation` | JSONB | 자산군별 스냅샷 `[{asset_class, value_krw}]` |
| `created_at` | timestamptz | `server_default=now()` |

- 값은 `get_portfolio()`의 `summary`(`total_value_krw`/`total_cost_krw`/
  `total_profit_loss_krw`/`total_cash_krw`) + `allocation`을 그대로 기록.
  별도 시세 계산 로직 없음.
- `allocation`은 v1 차트엔 미사용이나 **지금부터 저장**해야 후속 자산군 추세를
  백필 없이 그릴 수 있다.
- `ensure_schema`가 신규 DB에 자동 생성. 기존 dev DB는 부팅 시 create-only로
  생성됨(신규 테이블이라 ALTER 불필요).
- 모델 파일: `app/models/portfolio_snapshot.py`, `app/models/__init__.py` 등록.

## 2. 적재 — 고정 cron 스케줄러

- `app/services/scheduler/scheduler.py`에 **매일 KST 06:30** cron 잡 추가
  (`add_job(..., "cron", hour=6, minute=30, id="daily_snapshot")`).
  06:30 선택 이유: US 마감(~06:00 KST) 직후, KR 개장(09:00) 전 → 직전 사이클의
  안정적 종가. 기존 `alert_tick`(5분 interval)·1분 tick과 별개 잡.
- 잡 콜백 → `snapshot_service.capture_daily_snapshot(db)`:
  `get_portfolio()` 호출 → `build_snapshot_row`로 변환 → 오늘(KST) 날짜 **upsert**
  (행 있으면 덮어씀; cron은 하루 1회라 사실상 insert, 수동 재실행 시 멱등).
- 주말/휴장일도 매일 기록(사용자 결정). 휴장일은 직전 종가 반복으로 추세선이
  평평 — 정직한 표현. 시장 캘린더 게이팅 없음(KR/US 혼재 모호성 회피).
- 빈 포트폴리오(보유·현금 0)면 0값 행 기록(차트 연속성 유지).
- 스케줄러 핸들러 레지스트리(`schedules` 테이블/`feature_type`)는 사용하지 않음.
  이 잡은 target도 유저 설정도 없는 단일 고정 cron이라 직접 등록이 단순.

## 3. 백엔드 구조

신규 `app/services/snapshot/`:

- `snapshot_service.py`
  - `build_snapshot_row(portfolio: dict, today: date) -> dict` — **순수함수**.
    `get_portfolio()` 반환 dict와 날짜를 받아 테이블 컬럼 dict 생성(테스트 용이).
  - `capture_daily_snapshot(db) -> PortfolioSnapshot` — 조율: get_portfolio →
    build_snapshot_row → upsert.
- `snapshot_store.py`
  - `upsert_snapshot(db, row: dict) -> PortfolioSnapshot` — `date` 기준 upsert.
  - `list_snapshots(db, since: date | None) -> list[PortfolioSnapshot]` —
    `since` 이상 날짜, 오름차순. `None`이면 전체.

신규 `app/routers/trend.py`:

- `GET /api/trend?period=1M|3M|6M|1Y|ALL`
  → `[{date, total_value_krw, total_cost_krw, total_pl_krw, total_cash_krw, allocation}]`
  날짜 오름차순.
- `period_to_since(period: str, today: date) -> date | None` — 순수함수
  (1M=30일, 3M=90, 6M=180, 1Y=365, ALL=None). 미지/누락 값은 기본 1M로 폴백.
- `app/main.py`에 라우터 등록.

## 4. 프론트 — 대시보드 추세 차트

- 신규 `frontend/src/components/TrendChart.tsx`: **의존성 0, 자체 SVG**.
  - 총자산(`total_value_krw`) 단일 라인.
  - 기간 토글 버튼(1M/3M/6M/1Y/전체) → 선택 시 `period` 쿼리로 재조회(period별 fetch).
  - hover 툴팁(날짜 + 금액). 빈 데이터(스냅샷 0~1개)면 안내 문구.
  - 색/토큰은 기존 디자인 시스템(`--accent` 등) 재사용.
- `frontend/src/pages/Dashboard.tsx` 상단 요약 카드 아래에 배치, `GET /api/trend` 호출.
- API 클라이언트(`frontend/src/api/*`)에 `getTrend(period)` 추가.
- 자산군 스택차트는 이번 범위 제외. 데이터(`allocation`)는 적재만.

## 5. 데이터 흐름

```
cron(매일 06:30 KST)
  → capture_daily_snapshot(db)
      → get_portfolio(db)            # 실시간 시세 기준 집계
      → build_snapshot_row(...)      # 순수: dict → 컬럼
      → upsert_snapshot(...)         # portfolio_snapshots, date 멱등
GET /api/trend?period
  → list_snapshots(db, since)
  → 대시보드 TrendChart (SVG 라인 + 기간 토글)
```

## 6. 테스트 전략

- 순수함수: `build_snapshot_row`(요약/allocation 매핑), `period_to_since`(각 기간).
- 통합(invest_test 격리 스키마): `upsert_snapshot` 멱등(같은 날짜 2회 → 1행, 갱신),
  `list_snapshots` since 필터·정렬, `capture_daily_snapshot` 엔드투엔드(빈 포트폴리오
  0값 행 포함), `GET /api/trend` 라우트.
- 프론트: `npm run build` + `tsc` 통과(렌더 단위테스트는 기존 관례상 미보유).

## 7. 마이그레이션 / 운영 노트

- 신규 테이블이라 기존 dev DB는 부팅 시 `ensure_schema`가 자동 생성(ALTER 불필요).
- 실 스케줄 스모크: 가까운 시각으로 임시 변경해 1회 적재 확인 후 06:30 환원(사용자 확인).
- 과거 데이터는 없음 — **오늘부터** 쌓인다. 초기엔 점 1~2개라 차트가 비어 보일 수 있음(정상).
