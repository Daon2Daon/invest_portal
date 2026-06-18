# 가격 알림 — 설계 (spec B)

작성일: 2026-06-18
단계: 3단계(모니터링·알림)의 첫 기능. 선행: 스펙 A(보유/관심 IA + 자산 상세 허브, main 병합 완료) — 알림은 그 자산 상세 허브에 "가격 알림" 섹션으로 편입된다.
후속: 다른 자산별 모니터링 기능(위험신호 등)이 같은 디스패처/패턴을 참고.

## 목적

사용자가 자산별로 가격 도달 조건을 걸어두면, 앱이 장중에 주기적으로 시세를 확인하고 조건 충족 시 텔레그램으로 1회 알린다. 보유/관심 구분 없이 모든 자산에 적용된다.

기준(basis)을 절대가뿐 아니라 **평균 매입가·52주 고저점에 대한 상대 비율**로도 설정할 수 있어, "매입가 대비 15% 하락(손절)", "고점 대비 10% 하락" 같은 실전 조건을 직접 표현한다.

## 확정된 결정 (2026-06-18 브레인스토밍)

- **대상**: `assets`에 등록된 자산(보유/관심 무관). manual 자산은 `manual_price` 기준 시세 사용.
- **기준(basis) 4종**: `ABSOLUTE`(절대 목표가) / `PURCHASE_AVG`(평균매입가 대비 ±%) / `WEEK52_HIGH`(52주 고점 대비 ±%) / `WEEK52_LOW`(52주 저점 대비 ±%). 반복 변동률(REFERENCE)은 **범위 제외**.
- **모델 = `(basis, direction, value)`**: 목표가 = 기준가 × (1 ± value%), `ABSOLUTE`는 목표가 = value. `direction`=ABOVE/BELOW로 도달 방향 판정.
- **1회성 발동**: 조건 충족 시 1회 발송 후 비활성(`enabled=False`, `is_triggered=True`)으로 두고 목록에 "발동됨" 유지. 사용자가 **재무장(rearm)** 하면 다시 감시. (변동률 반복 모니터링 없음)
- **모니터링 주기 = 5분, 해당 시장 개장(거래일+장중)에만**. 기존 1분 tick(차트 스케줄)과 별개의 APScheduler 5분 잡.
- **아키텍처(접근 A)**: 기존 scheduler/store/dispatcher 관례 복제 — 모델 + store + 순수 평가함수 + 디스패처 + 라우터로 분해.
- **신규 의존성** `pandas_market_calendars`를 requirements에 추가(현재 누락, my-assistant에선 사용).
- **UI**: 자산 상세 허브(`AssetDetail.tsx`)에 "가격 알림" 섹션으로 편입(별도 전역 페이지 없음 — YAGNI).

## 아키텍처

### 데이터 모델 — 신규 테이블 `invest.price_alerts`

`ensure_schema`가 부팅 시 멱등 생성(신규 마이그레이션 없음). `models/__init__.py`에 `PriceAlert` 등록.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `alert_id` | PK | |
| `asset_id` | INTEGER FK→assets.asset_id (ondelete CASCADE), NOT NULL, INDEX | 한 자산에 복수 알림 허용(UNIQUE 없음) |
| `basis` | TEXT | `ABSOLUTE` / `PURCHASE_AVG` / `WEEK52_HIGH` / `WEEK52_LOW` |
| `direction` | TEXT | `ABOVE`(이상 도달) / `BELOW`(이하 도달) |
| `value` | NUMERIC NOT NULL | ABSOLUTE=목표가(자산 통화), 그 외=기준 대비 % |
| `enabled` | BOOLEAN NOT NULL default True | |
| `is_triggered` | BOOLEAN NOT NULL default False | 1회성 발동 표시 |
| `triggered_at` | TIMESTAMP(tz) NULL | |
| `last_notified_at` | TIMESTAMP(tz) NULL | |
| `note` | TEXT NULL | 사용자 메모(선택) |
| `created_at` / `updated_at` | TIMESTAMP(tz) | server_default now |

### 순수 평가 — `app/services/alert/evaluator.py`

네트워크/DB 없이 숫자만 다룬다(단위테스트 핵심).

```python
def compute_target(basis: str, direction: str, value: float, basis_price: float | None) -> float:
    """ABSOLUTE → value. 그 외 → basis_price * (1 + sign*value/100), sign=+1(ABOVE)/-1(BELOW)."""
    if basis == "ABSOLUTE":
        return value
    sign = 1.0 if direction == "ABOVE" else -1.0
    return basis_price * (1.0 + sign * value / 100.0)

def is_fired(direction: str, current_price: float, target_price: float) -> bool:
    """ABOVE → current >= target, BELOW → current <= target."""
    return current_price >= target_price if direction == "ABOVE" else current_price <= target_price
```

예시: "고점 대비 10% 하락" = WEEK52_HIGH/BELOW/10 → target=high×0.90, price≤target 시 발동. "매입가 20% 상승(익절)" = PURCHASE_AVG/ABOVE/20 → target=avg×1.20.

### 기준가 조회 — `app/services/alert/basis.py`

```python
async def resolve_basis_price(db, asset, basis: str) -> float | None:
    #  ABSOLUTE     → None (compute_target가 value 직접 사용)
    #  PURCHASE_AVG → 보유 lot 가중평균 매입가, 보유 없으면 None
    #  WEEK52_HIGH  → 1년 일봉 max(High), 이력 없으면 None
    #  WEEK52_LOW   → 1년 일봉 min(Low),  이력 없으면 None
```

- PURCHASE_AVG: `select(Holding).where(asset_id==)` → `Σ(qty*price)/Σqty`.
- WEEK52: `history_service.get_history(asset, 365)` 사용. yfinance 호출 절감 위해 **자산별 in-process TTL 캐시**(기본 1시간): `_WEEK52_CACHE[asset_id] = (high, low, fetched_at)`. 테스트용 `clear_week52_cache()` 제공.
- WEEK52 목표가는 매 평가마다 최신 고저점으로 재산출 → 트레일링 효과.

### 메시지 — `app/services/alert/message.py`

```python
def build_message(asset, alert, current_price: float, target_price: float) -> str:
    """텔레그램 HTML. 통화별 표기(₩ 정수 / 그 외 소수 2자리). basis·direction을 사람이 읽는 문구로."""
```
- 예: `🔔 <b>삼성전자</b> (005930·KR)\n조건: 평균매입가 대비 -15% 도달\n현재가 59,500원 ≤ 목표 59,500원`

### 디스패처 — `app/services/alert/alert_dispatcher.py`

```python
async def evaluate_tick() -> None:
    now = datetime.now(KST)
    async with SessionLocal() as db:
        # 텔레그램 미설정이면 평가 자체를 건너뜀(조용히 종료)
        alerts = enabled & not is_triggered 알림 + asset(is_active) 조인 로드
        asset별 그룹화
        for asset, group:
            if not is_market_open(asset.market, now): continue   # 휴장/장마감 skip
            quote = get_quote(asset)
            if quote.status != "ok" or not quote.price: continue  # 시세 실패 skip
            for alert in group:
                try:
                    basis_price = await resolve_basis_price(db, asset, alert.basis)
                    if basis_price is None and alert.basis != "ABSOLUTE": continue
                    target = compute_target(alert.basis, alert.direction, float(alert.value), basis_price)
                    if is_fired(alert.direction, quote.price, target):
                        ok = await telegram_service.send_message(db, build_message(...))
                        if ok:
                            alert.enabled = False; alert.is_triggered = True
                            alert.triggered_at = now; alert.last_notified_at = now
                            await db.commit()
                        await asyncio.sleep(2)   # 텔레그램 rate-limit 여유
                except Exception:                # 한 건 실패가 나머지를 막지 않음
                    await db.rollback(); log.warning(...)
```

- 자산당 시세 1회만 조회(그룹화). 건별 try/except + rollback(기존 `dispatcher.py` 철학).

### 개장 판정 — `app/services/market/market_hours.py`

```python
def is_market_open(market: str, now: datetime) -> bool:
    #  CRYPTO → 항상 True
    #  US → NYSE 캘린더, now(UTC 환산)가 당일 [market_open, market_close] 구간 내 (반일장 자동 반영)
    #  KR → XKRX, JP → JPX 동일 방식
    #  미지 시장/라이브러리 오류 → True (fail-open: 알림 누락 방지)
```
- `pandas_market_calendars.get_calendar(name)` 결과를 모듈 캐시. `cal.schedule(date, date)`의 `market_open/market_close`(tz-aware)와 `now`를 UTC로 비교. JP 점심 휴장은 단순화해 무시(개인용 영향 경미).
- `now`를 인자로 받아 순수·결정적 → 고정 datetime으로 단위테스트.

### CRUD store — `app/services/alert/alert_store.py`

`list_active_with_assets(db)`, `create`, `get`, `update`, `rearm`, `delete`, `list_by_asset(db, asset_id)`. 라우터·디스패처가 공유(schedule_store 패턴).

### API 라우터 — `app/routers/alerts.py` (`/api/alerts`)

| 메서드 | 경로 | 동작 |
|--------|------|------|
| POST | `/api/alerts` | 생성 `{asset_id, basis, direction, value, note?}`. Pydantic enum·`value>0` 검증 + 기준별 사전검증(아래) |
| GET | `/api/alerts?asset_id=` | 자산별 알림 목록. 각 알림에 **현재 목표가·현재가·발동상태 라이브 계산** 포함 |
| PUT | `/api/alerts/{id}` | value/direction/note/enabled 수정 |
| POST | `/api/alerts/{id}/rearm` | 재무장: `enabled=True, is_triggered=False, triggered_at=None` |
| DELETE | `/api/alerts/{id}` | 삭제 |

생성 시 사전검증(위반 → 422):
- `PURCHASE_AVG`: 해당 자산에 보유 lot이 1개 이상이어야 함.
- `WEEK52_*`: 자산 `data_source != "manual"`(이력 조회 가능해야 함).
- 자산 없음 404.

`schemas/alert.py`: `AlertCreate`, `AlertUpdate`, `AlertOut`(basis/direction Literal).
`main.py`에 alerts 라우터 등록. `scheduler.py`에 5분 잡 추가:
```python
_scheduler.add_job(evaluate_tick, "interval", minutes=5, id="alert_tick",
                   replace_existing=True, max_instances=1, coalesce=True)
```

### 프론트엔드 — 자산 상세 허브에 "가격 알림" 섹션

`frontend/src/pages/AssetDetail.tsx`에 섹션 추가(별도 페이지 없음):
- **목록**: 기준 · 방향 · 값 · 현재 목표가(라이브) · 상태(활성/발동됨) · 액션(재무장·삭제).
- **추가 폼**: 기준 선택 → 방향(이상/이하) → 값 입력(ABSOLUTE는 "가격", 그 외 "%"로 단위 라벨 전환). 기준 가용성은 자산 상태로 선제 제한: 보유 lot 없으면 `PURCHASE_AVG` 비활성, manual이면 `WEEK52_*` 비활성(서버 422 선제 차단).
- 헤더의 `held`(스펙 A `assetDetail`)로 PURCHASE_AVG 가용성 판단, `asset.data_source`로 WEEK52 가용성 판단.
- `api.ts`에 `listAlerts(assetId)`, `createAlert`, `updateAlert`, `rearmAlert`, `deleteAlert` + `Alert`/`AlertCreate` 타입 추가.

## 데이터 흐름

```
[5분 tick] evaluate_tick
  └ 활성·미발동 alert + asset 로드 → asset별 그룹
     └ is_market_open? → get_quote → resolve_basis_price → compute_target → is_fired?
        └ 발동: telegram send_message → enabled=False/is_triggered=True 커밋

[UI] AssetDetail 가격 알림 섹션
  ├ GET /api/alerts?asset_id  (라이브 목표가 포함)
  ├ POST /api/alerts          (기준별 사전검증)
  ├ POST /api/alerts/{id}/rearm
  └ DELETE /api/alerts/{id}
```

## 에러 처리

- 디스패처: 예외를 던지지 않고 `logging.warning`으로 흡수(스케줄러 잡 보호). 텔레그램 미설정 시 tick 조용히 종료.
- 생성 검증 실패 422, 자산없음 404, 텔레그램 미설정은 알림 발송 시점에만 의미(생성은 무관).
- manual 자산 + WEEK52는 생성 단계 차단 → 런타임 None skip은 방어선.
- 시세 실패(status!=ok)·기준가 None은 해당 tick에서 skip(다음 tick 재시도).

## 테스트 계획

- `test_market_hours.py` — US/KR/JP/CRYPTO 개장·주말·공휴일·반일장(고정 datetime 주입), 미지 시장 fail-open.
- `test_alert_evaluator.py` — compute_target 4기준×방향, ABSOLUTE 무시 basis_price, is_fired 경계값.
- `test_alert_basis.py` — PURCHASE_AVG 가중평균, 보유0→None, WEEK52 max/min + TTL 캐시 동작, manual/이력없음→None.
- `test_alert_store.py` — CRUD + rearm 상태 리셋.
- `test_alert_dispatcher.py` — 가짜 quote/telegram 주입: 발동→상태갱신, 장마감 skip, 시세실패 skip, 자산당 quote 1회, 기준가 None skip, 건별 장애격리.
- `test_alerts_api.py` — 생성/목록(라이브 목표가)/수정/재무장/삭제 + 검증 에러(PURCHASE_AVG 보유0, WEEK52 manual, value≤0).
- 프론트: `tsc`/빌드 통과 + 수동 스모크(허브 알림 섹션 추가/재무장/삭제). API 계약은 백엔드 테스트가 보증.

## 비목표 (명시)

- 반복 변동률(REFERENCE) 알림.
- 전역 알림 통합 페이지(자산 상세 허브 섹션으로 충분).
- 사용자 설정 모니터링 주기(5분 고정).
- 쿨다운 기반 자동 재무장(수동 재무장만).
- 이메일/푸시 등 텔레그램 외 채널.

## 영향 받는 파일 (요약)

신규
- `app/models/price_alert.py`
- `app/services/alert/__init__.py`, `evaluator.py`, `basis.py`, `message.py`, `alert_store.py`, `alert_dispatcher.py`
- `app/services/market/market_hours.py`
- `app/routers/alerts.py`, `app/schemas/alert.py`
- `tests/test_market_hours.py`, `test_alert_evaluator.py`, `test_alert_basis.py`, `test_alert_store.py`, `test_alert_dispatcher.py`, `test_alerts_api.py`

수정
- `app/models/__init__.py` — PriceAlert 등록
- `app/services/scheduler/scheduler.py` — 5분 alert_tick 잡 추가
- `app/main.py` — alerts 라우터 등록
- `requirements.txt` — pandas_market_calendars 추가
- `frontend/src/api.ts` — alert 함수·타입
- `frontend/src/pages/AssetDetail.tsx` — 가격 알림 섹션
