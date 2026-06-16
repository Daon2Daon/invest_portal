# 2d: 스케줄 자동 발송 — 설계 (spec)

작성일: 2026-06-16
단계: 2단계(chartbot + 텔레그램)의 2d. 선행: 2a+2b(차트 생성 + 텔레그램 발송), 2c(AI 차트 분석) — 모두 main 병합 완료.
후속: 3단계(AI 리포트·투자저널·위험신호)의 다른 발송 기능이 본 디스패처·테이블을 공유.

## 목적

종목별로 설정한 발송 시각·요일에 맞춰, 차트(+2c AI 분석)를 텔레그램으로 **자동 발송**한다.
사용자는 차트 화면에서 종목별 스케줄을 설정하고, 앱이 백그라운드에서 일정에 맞춰 발송한다.

## 확정된 결정

- **중앙 집중식 디스패처:** 종목별 APScheduler 잡을 개별 등록하지 않고, 1분 간격 tick 잡 1개가
  DB의 `schedules` 테이블을 매번 읽어 due한 항목을 순차 발송. 여러 기능이 같은 시각에 발송을
  걸어도 한 건씩 순차 처리되어 충돌·텔레그램 rate limit이 없다.
- **개별 기능 메뉴에서 설정:** 통합 스케줄 메뉴를 따로 만들지 않고, 차트 페이지 안에서 종목별로
  스케줄을 설정(향후 다른 기능도 자기 메뉴에서 설정 → 같은 테이블에 행 추가).
- **종목당 1개 스케줄** (UNIQUE 제약).
- **잡스토어 = 메모리:** 진실의 원천은 `schedules` 테이블. 부팅 시 tick 잡 1개만 등록.
- **타임존 = KST 고정**(Asia/Seoul). send_time은 KST 벽시계.
- **미스된 실행:** 그날 안에 늦게라도 발송(자정 넘기면 전날 건 폐기). 방해금지(quiet hours)
  로직 없음(ytdb 레슨: 사용자가 정한 예약 시각은 이미 받기 편한 시간).

## 아키텍처

### 데이터 모델 — 신규 테이블 `invest.schedules`

ensure_schema가 부팅 시 자동 생성(신규 마이그레이션 없음). 범용 스키마로 향후 발송 기능이 공유.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `schedule_id` | PK | |
| `feature_type` | TEXT | 현재 `"chart_analysis"` 고정, 향후 확장 |
| `target_id` | INTEGER | chart_analysis면 `asset_id` |
| `send_time` | TEXT `"HH:MM"` | KST 벽시계 |
| `days_of_week` | TEXT | `"0,1,2,3,4"` (월=0…일=6) 콤마 리스트 |
| `enabled` | BOOLEAN | |
| `last_run_date` | DATE (nullable) | 마지막 발송한 KST 날짜 — 같은 날 중복 방지 |
| `created_at` / `updated_at` | TIMESTAMP | |

- **UNIQUE(feature_type, target_id)** — 종목당 1개 스케줄.
- 모델: `app/models/schedule.py` (기존 모델 패턴 따름), `app/models/__init__.py`에 export.

### 신규 패키지 `app/services/scheduler/`

**`scheduler.py`** (APScheduler 래퍼)
- `AsyncIOScheduler(timezone="Asia/Seoul")` 모듈 싱글톤. FastAPI 이벤트 루프 위에서 동작.
- 잡스토어 = 메모리(기본). 부팅 시 tick 잡 1개만 등록.
- `start_scheduler()`: 싱글톤 생성 → tick 잡 등록
  (`add_job(dispatch_tick, "interval", minutes=1, id="dispatch_tick", replace_existing=True, max_instances=1, coalesce=True)`) → `start()`.
- `shutdown_scheduler()`: `scheduler.shutdown(wait=False)`.

**`dispatcher.py`** (tick 본체 + 핸들러 레지스트리)
- `async dispatch_tick()`: 자기 `AsyncSession`(`SessionLocal()`) 열고 → `enabled=True` 스케줄 조회 →
  각 `_is_due(schedule, now_kst)` 판정 → due인 것들을 **순차 처리(건 사이 `asyncio.sleep`)** →
  핸들러 성공 시 `last_run_date = today_kst` 갱신·커밋. 개별 발송 실패는 로그만 남기고 다음 건 진행
  (한 종목 실패가 나머지를 막지 않음).
- `_is_due(schedule, now_kst) -> bool` (순수 함수, 단위테스트 대상):
  `enabled` ∧ `now.weekday() in days_of_week` ∧ `now.time() >= parse(send_time)` ∧
  `last_run_date != now.date()` → True.
- `_HANDLERS = {"chart_analysis": handle_chart_analysis}` — `feature_type`별 async 핸들러.
  미지의 타입은 경고 로그 후 skip. **여러 기능 공유의 확장점.**
- `async handle_chart_analysis(db, schedule)`: `target_id`로 asset 조회 →
  `chart_dispatch.send_chart_telegram(db, asset)` 호출. asset 없으면 경고 로그 후 skip.

### send-telegram 로직 재사용 (리팩터링)

현재 차트+AI 발송 로직은 `send_telegram` 라우트 핸들러 안에 있다(`app/routers/charts.py`).

- 신규 `app/services/notification/chart_dispatch.py` →
  `async def send_chart_telegram(db, asset) -> dict`: 차트 2장 발송 + best-effort AI 분석 발송
  (기존 라우트 본문 로직 이동). 반환 `{"sent", "ok", "analysis_sent"}`.
  `TelegramNotConfigured`는 그대로 전파(라우트는 409로, 디스패처는 잡아서 로그).
- `POST /api/charts/{id}/send-telegram` 라우트는 asset 조회 후 이 함수를 호출하는 얇은 래퍼로 축소.
- 디스패처 핸들러도 동일 함수 호출 → **수동 발송과 자동 발송이 같은 코드 경로**.

### API (라우터 변경) — `app/routers/charts.py` 추가

- `GET /api/charts/{asset_id}/schedule` → `{send_time, days_of_week: [int...], enabled}` 또는 `null`(미설정).
- `PUT /api/charts/{asset_id}/schedule` (body: `send_time`, `days_of_week`, `enabled`) → upsert
  (UNIQUE로 종목당 1개). 변경은 **DB만 갱신**(tick이 매번 DB를 읽으므로 잡 재등록 불필요).
- `DELETE /api/charts/{asset_id}/schedule` → 삭제.
- 입력 검증: `send_time`은 `HH:MM` 형식, `days_of_week`는 0~6 정수 리스트(빈 리스트면 발송 안 됨,
  저장은 허용). 잘못된 형식 → 422. asset 없음 → 404.

### app/main.py lifespan

`ensure_schema` 뒤에 `start_scheduler()`, 종료 시 `shutdown_scheduler()`.
테스트는 `ASGITransport`라 lifespan 미발동 → 스케줄러가 뜨지 않음(테스트 격리).

### 프론트엔드

**`frontend/src/pages/Charts.tsx`** — "자동 발송 스케줄" 섹션 추가(종목 선택 영역 아래)
- 발송 시각 `<input type="time">`(HH:MM), 요일 체크박스 7개(월~일), 활성화 토글, 저장/삭제 버튼 + 상태 메시지.
- 종목 변경 시 해당 종목 스케줄 로드(없으면 빈 폼).

**`frontend/src/api.ts`** — `getSchedule(id)`, `saveSchedule(id, payload)`, `deleteSchedule(id)` 추가.

## 데이터 흐름

```
[부팅] lifespan → ensure_schema → start_scheduler (tick 잡 1개 등록)

[매 1분] dispatch_tick
  → SessionLocal()로 AsyncSession
  → enabled 스케줄 조회
  → for each: _is_due(schedule, now_kst)?
      → due면 _HANDLERS[feature_type](db, schedule)
        → chart_analysis: handle_chart_analysis
          → asset 조회 → chart_dispatch.send_chart_telegram(db, asset)
            → (기존) 일봉/주봉 send_photo + best-effort AI 분석 send_message
      → 성공 시 last_run_date = today_kst, 커밋
      → 건 사이 asyncio.sleep

[차트 페이지] 스케줄 설정
  → PUT /api/charts/{id}/schedule → schedules upsert (DB만 갱신)

[차트 페이지] 수동 발송(기존)
  → POST /api/charts/{id}/send-telegram → chart_dispatch.send_chart_telegram (동일 경로)
```

## 에러 처리

- 디스패처 개별 발송 실패(차트/텔레그램/AI 오류): 로그만 남기고 다음 건 진행. tick 전체는 죽지 않음.
  실패 시 `last_run_date`를 갱신하지 않아 다음 tick에서 재시도(그날 안).
- `TelegramNotConfigured`: 디스패처는 잡아서 경고 로그(자동 발송은 조용히 skip). 수동 라우트는 409.
- asset 없음(스케줄은 있는데 자산 삭제됨): 경고 로그 후 skip.
- 스케줄 API: 잘못된 send_time/days_of_week → 422. asset 없음 → 404.
- `max_instances=1` + `coalesce=True`: tick이 길어져도 중복/누적 실행 방지.

## 테스트

**단위(pytest)**
- `_is_due()`: 요일 불일치 / 시각 이전 / 오늘 이미 실행(last_run_date=today) / 비활성 / due 케이스.
- 스케줄 API(실 test DB): upsert→get→delete, 잘못된 형식 422, asset 없음 404.
- `send_chart_telegram` 추출 후 기존 `send-telegram` 라우트 테스트 회귀 없음 + 디스패처 핸들러가
  동일 함수를 호출하는지(함수 mock).
- `dispatch_tick`: due 스케줄에 핸들러 호출 + 성공 시 `last_run_date` 갱신, 실패 시 미갱신(핸들러 mock).
- APScheduler 내부 동작은 테스트하지 않음.

**스모크(실 DB/실 게이트웨이, 설정 시)**
- 가까운 시각으로 스케줄 등록 → tick이 차트+분석을 텔레그램으로 발송하는지 확인.

빌드: `cd frontend && npm run build` 통과.

## YAGNI (이번 범위 제외)

- 종목당 복수 스케줄(종목당 1개).
- PG 잡스토어(메모리 + DB 테이블이 진실의 원천).
- 기능별 별도 테이블(범용 `schedules` 하나).
- 방해금지(quiet hours) — 예약 발송엔 불필요(ytdb 레슨).
- 타임존 선택 UI(KST 고정).
- 자정 넘긴 catch-up.
- 발송 이력 로그 테이블(3단계에서 필요 시).

## 영향받는 파일 요약

- 신규: `app/models/schedule.py`, `app/services/scheduler/__init__.py`,
  `app/services/scheduler/scheduler.py`, `app/services/scheduler/dispatcher.py`,
  `app/services/notification/chart_dispatch.py`
- 수정: `app/models/__init__.py`(Schedule export — ensure_schema가 `import app.models`로 메타데이터에
  등록된 모든 모델을 `create_all`하므로 export만으로 새 테이블 자동 생성), `app/main.py`(lifespan),
  `app/routers/charts.py`(스케줄 API + 라우트 축소)
- 신규 테스트: `tests/test_scheduler_dispatcher.py`, `tests/test_charts_schedule.py`
- 수정 테스트: `tests/test_charts_analyze.py`(send_chart_telegram 추출 반영)
- 프론트: `frontend/src/pages/Charts.tsx`, `frontend/src/api.ts`
- 의존성: `requirements.txt`에 `apscheduler` 추가. 마이그레이션 없음(ensure_schema 자동 생성).
