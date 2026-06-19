# 증시 마감 요약 푸시 — 설계 (spec)

작성일: 2026-06-20
단계: my-assistant 미이식 잔여 #1. 선행: 2d 스케줄 자동 발송(중앙 디스패처)·가격 알림(market_hours)·보유/관심 IA — 모두 main 병합 완료.
후속: 3단계(AI 리포트·투자저널·위험신호).

## 목적

US·KR 증시 마감 시각에 맞춰, 주요 지수와 보유/관심 종목의 일·주·월 변동률 및 52주 고점 대비를 텔레그램으로 요약 발송한다. my-assistant `finance_bot`의 증시 알림을 현재 앱 구조(중앙 스케줄러·history_service·telegram_service)로 이식한다.

## 확정된 결정 (2026-06-20 브레인스토밍)

- **구성**: 주요 지수 + 보유종목 + 관심종목. 각 종목은 일/주/월 변동률 + 52주 고점 대비.
- **시장별 요약**: US 요약·KR 요약을 각각 별도 시각·요일로 발송(마감 시각이 달라 실사용에 맞음). v1 대상 = **US, KR**(JP/코인은 비목표).
- **지수(고정)**: US = ^GSPC(S&P 500)·^IXIC(NASDAQ)·^DJI(다우), KR = ^KS11(KOSPI)·^KQ11(KOSDAQ).
- **스케줄링(접근 A)**: 기존 `schedules` 테이블 + 1분 tick 디스패처 재사용. 시장별 `feature_type`로 구분, 신규 테이블 없음.
- **거래일에만**: 휴장일은 발송 스킵(그날 재시도/스팸 없음).
- **구성 UI**: 설정 페이지의 "증시 마감 요약" 섹션(US/KR 각각). 즉시 발송(테스트) 버튼 포함.
- **비목표**: JP/코인 요약, 사용자 지정 지수, 통합 단일 요약, 발송 이력 로그.

## 아키텍처

### 스케줄 모델 — 기존 `schedules` 재사용

신규 테이블 없음. `app/services/scheduler/schedule_store.py`에 상수 추가:

```python
FEATURE_SUMMARY_US = "market_summary_us"
FEATURE_SUMMARY_KR = "market_summary_kr"
```

- 시장별 1개 행: `feature_type=FEATURE_SUMMARY_US|KR`, `target_id=0`(미사용 센티넬), `send_time`("HH:MM" KST), `days_of_week`("0..6"), `enabled`, `last_run_date`.
- UNIQUE(feature_type, target_id)라 시장당 1행. 기존 `get_schedule/upsert_schedule/delete_schedule/list_enabled`을 `target_id=0`으로 그대로 사용.
- 디스패처(`dispatch_tick`)·`_is_due`(요일·시각 도달·당일 중복방지) 변경 없음. `HANDLERS`(handlers.py)에 두 핸들러 등록.

### 거래일 체크 — `app/services/market/market_hours.py`에 추가

```python
def is_trading_day(market: str, now: datetime) -> bool:
    """해당 시장의 now(시장 tz 환산) 날짜가 거래일인지. CRYPTO/미지 시장/오류 → True(fail-open)."""
```

- `_MARKET_TZ = {"US":"America/New_York","KR":"Asia/Seoul","JP":"Asia/Tokyo"}`로 `now`를 시장 tz로 환산해 날짜를 얻고, 캘린더(NYSE/XKRX/JPX) `schedule(date,date)` 비어있지 않으면 거래일.
- US 요약은 KR 아침 발송이라 `now`(KST)를 ET로 환산하면 직전 미국 거래일 날짜가 되어 의도대로 동작. KR 요약은 KST 날짜.
- 기존 `is_market_open`과 캘린더 캐시(`_cal_cache`)·`_CAL_NAMES` 공유.

### 콘텐츠 빌더 — 신규 `app/services/market_summary/`

- `indices.py`
  ```python
  INDICES = {"US": [("^GSPC","S&P 500"), ("^IXIC","NASDAQ"), ("^DJI","다우")],
             "KR": [("^KS11","KOSPI"), ("^KQ11","KOSDAQ")]}
  async def index_lines(market) -> list[dict]   # [{name, price, change_pct}]  (yfinance history 5d, to_thread)
  ```
  - 지수는 자산(DB)이 아니므로 yfinance를 직접 호출(최근 2거래일 종가로 전일대비%). 실패한 지수는 결과에서 제외.
- `changes.py`
  ```python
  async def asset_stats(asset) -> dict | None
  #  history_service.get_history(asset, 370) 사용. 반환:
  #  {current, daily_pct, weekly_pct, monthly_pct, wk52_high, wk52_drop_pct}
  #  daily=직전 종가 대비, weekly=약 5거래일 전 대비, monthly=약 21거래일 전 대비,
  #  wk52_drop_pct=(current - 52주 max(High)) / max(High) * 100  (항상 ≤0)
  #  이력 부족/없음(manual 등) → None
  ```
- `message.py`
  ```python
  def build_message(market, indices, holdings_stats, watchlist_stats) -> str
  #  텔레그램 HTML. [주요 지수] 섹션 + [보유 종목]/[관심 종목] 섹션.
  #  통화: KR은 '원'(정수), US는 '$'(소수2). 변동은 +/− 부호 + 📈(상승)/📉(하락) 고정.
  ```
- `summary_service.py`
  ```python
  async def build_and_send(db, market) -> dict
  #  1) index_lines(market)
  #  2) 그 시장의 활성 자산을 보유/관심으로 분류(held_asset_ids 재사용), 각 asset_stats
  #  3) build_message → telegram_service.send_message
  #  종목 단위 실패는 스킵하고 전체 발송 진행. TelegramNotConfigured는 호출자가 구분(수동=409, 스케줄=swallow).
  #  반환 {market, sent: bool, indices: n, holdings: n, watchlist: n}
  ```

### 스케줄러 핸들러 — `app/services/scheduler/handlers.py`

```python
async def handle_market_summary(db, schedule):
    market = "US" if schedule.feature_type == FEATURE_SUMMARY_US else "KR"
    if not is_trading_day(market, datetime.now(KST)):
        return                      # 휴장일 → 발송 없이 반환(디스패처가 last_run 기록)
    try:
        await summary_service.build_and_send(db, market)
    except telegram_service.TelegramNotConfigured:
        log.info("텔레그램 미설정 — 증시 요약 발송 생략")   # swallow → 재시도 스팸 방지

HANDLERS = {..., FEATURE_SUMMARY_US: handle_market_summary, FEATURE_SUMMARY_KR: handle_market_summary}
```

### API — 신규 `app/routers/market_summary.py` (`/api/market-summary`)

| 메서드 | 경로 | 동작 |
|--------|------|------|
| GET | `/api/market-summary/{market}/schedule` | 시장 스케줄 조회(없으면 null). market∈{US,KR} 아니면 404 |
| PUT | `/api/market-summary/{market}/schedule` | `{send_time, days_of_week, enabled}` 업서트(send_time HH:MM·요일 0~6 검증) |
| DELETE | `/api/market-summary/{market}/schedule` | 삭제 |
| POST | `/api/market-summary/{market}/send` | 즉시 발송(테스트). 텔레그램 미설정 409 |

- `market`→`feature_type` 매핑, `target_id=0`으로 `schedule_store` 재사용. ScheduleIn 검증은 charts 라우터의 패턴 재사용.
- `main.py`에 라우터 등록.

### 프론트엔드 — 설정 페이지 섹션

- `frontend/src/pages/Settings.tsx`에 "증시 마감 요약" 섹션: US·KR 두 블록(발송 시각·요일 토글·활성화 체크·저장/삭제·"지금 발송"). 차트 스케줄 UI 패턴 재사용.
- `api.ts`: `getMarketSummarySchedule(market)`, `saveMarketSummarySchedule(market, body)`, `deleteMarketSummarySchedule(market)`, `sendMarketSummary(market)`.

## 데이터 흐름

```
[1분 tick] dispatch_tick → _is_due(market_summary_us/kr 행) → HANDLERS[feature_type]
  → is_trading_day? → summary_service.build_and_send(market)
       → index_lines(yfinance) + (held/watch asset_stats via history_service) → message → telegram send
  → (성공/휴장/미설정 모두 정상 반환) 디스패처가 last_run_date=today 기록

[설정 UI] /api/market-summary/{US|KR}/schedule (GET/PUT/DELETE), /send(즉시)
```

## 에러 처리

- 휴장일: 핸들러가 발송 없이 반환 → 디스패처가 정상 종료로 보고 `last_run_date` 기록(스팸 없음).
- 지수/종목 개별 실패: 해당 항목만 제외하고 메시지 발송 진행.
- 텔레그램 미설정: 스케줄 경로는 swallow(로그), 수동 `/send`는 409 반환.
- 잘못된 market 경로: 404. 잘못된 시각/요일: 422.

## 테스트 계획

- `test_market_hours.py`(추가) — `is_trading_day` 거래일/주말/휴장/CRYPTO/미지(fail-open).
- `test_summary_changes.py` — `asset_stats` 합성 이력으로 일/주/월·52주 고점대비 계산, 이력부족→None.
- `test_summary_indices.py` — yfinance patch로 `index_lines` 형태·전일대비% (실패 지수 제외).
- `test_summary_message.py` — 통화별 표기, 지수/보유/관심 섹션, 52주 drop 표기.
- `test_summary_service.py` — 시장 필터(US/KR 분리), held/watch 분류, 종목 실패 스킵, telegram 호출(patch).
- `test_market_summary_api.py` — 스케줄 GET/PUT/DELETE(schedule_store mock), market 검증(404), 시각 검증(422), `/send`(build_and_send mock + 텔레그램 미설정 409).
- 프론트: `tsc`/빌드 + 수동 스모크(설정에서 시각 등록·즉시 발송).

## 영향 받는 파일 (요약)

신규
- `app/services/market_summary/__init__.py`, `indices.py`, `changes.py`, `message.py`, `summary_service.py`
- `app/routers/market_summary.py`
- `tests/test_summary_changes.py`, `test_summary_indices.py`, `test_summary_message.py`, `test_summary_service.py`, `test_market_summary_api.py`

수정
- `app/services/market/market_hours.py` — `is_trading_day` + `_MARKET_TZ`
- `app/services/scheduler/schedule_store.py` — FEATURE_SUMMARY_US/KR 상수
- `app/services/scheduler/handlers.py` — handle_market_summary + 레지스트리 2개 등록
- `app/main.py` — market_summary 라우터 등록
- `tests/test_market_hours.py` — is_trading_day 테스트 추가
- `frontend/src/api.ts`, `frontend/src/pages/Settings.tsx`
