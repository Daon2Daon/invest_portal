# 변동성(REFERENCE) 알림 설계

작성일: 2026-06-20

## 배경 / 동기

테스트 버전 `my_assistant`의 `PERCENT_CHANGE` 가격 알림(종목별 변동성 모니터링)이 현재 앱에 미이식. 현재 앱 가격 알림은 4기준(`ABSOLUTE`/`PURCHASE_AVG`/`WEEK52_HIGH`/`WEEK52_LOW`)을 1회성 발동+재무장 모델로 지원하나, "이동 기준가 대비 ±X% 변동 시 반복 알림"(트레일링 급변동 감지)은 가격알림 설계 당시 `REFERENCE`로 명명해 의도적으로 제외했던 항목이다. 이를 추가한다.

`my_assistant` 원본 동작(`app/services/bots/finance_bot.py` `check_price_alerts`):
- 첫 평가 시 `reference_price = 현재가`로 초기화(미발동).
- `|(현재가-기준가)/기준가|*100 ≥ target_percent`이면 발동(급등·급락 **양방향**).
- 발동 후 `reference_price`를 현재가로 **재설정해 계속 모니터링**(반복). 목표가/손절가(1회성)와 달리 `is_triggered`로 표시하지 않음.

## 설계 결정 (브레인스토밍 2026-06-20)

1. **기준가 동작 = 트레일링 반복**: 첫 관측 시 현재가로 lazy-init, ±X% 변동마다 발동 후 현재가로 재설정해 계속 감시.
2. **발동 방향 = 양방향**: `|변동률| ≥ X%`면 급등·급락 모두 발동. 메시지에 상승/하락 구분 표기.
3. **UI = 기준가 ±X% 밴드 표시**: 공용 알림 테이블 목표가 열에 `기준가 ±X%`(예: `50,000 ±5%`)로 표시.
4. **통합 방식 = 기존 `PriceAlert` 모델에 `REFERENCE` 기준 추가**(별도 테이블/디스패처 아님). 5분 tick·장중 게이팅·텔레그램·알림 허브·배지 전부 재사용.

## 데이터 모델

`app/models/price_alert.py` `PriceAlert`에 컬럼 1개 추가:

```python
reference_price: Mapped[float | None] = mapped_column(Numeric)  # REFERENCE 트레일링 기준가
```

- 신규 DB: `ensure_schema`가 모델 기준 자동 생성.
- 기존 dev DB: `ALTER TABLE invest.price_alerts ADD COLUMN IF NOT EXISTS reference_price NUMERIC` (in-place, 기존 알림 데이터 보존). `ensure_schema`는 create-only라 기존 DB는 이 ALTER 수동 적용 필요.
- 기존 4기준 알림은 이 컬럼 미사용(NULL 유지).

REFERENCE 알림 필드 규약:
- `basis = "REFERENCE"`
- `direction = "BOTH"` (센티넬; 양방향)
- `value` = 변동 임계 %(양수, 예: 5.0)
- `reference_price` = 트레일링 기준가(최초 NULL → lazy-init)
- `is_triggered`는 항상 False 유지(반복 감시라 발동 표시 안 함)

## 평가 로직 — `app/services/alert/evaluator.py`

신규 순수 함수 추가(네트워크/DB 없음):

```python
def ref_fired(reference_price: float, current_price: float, value: float) -> bool:
    """기준가 대비 |변동률| >= value(%) 이면 True. 양방향, 경계 포함."""
    if reference_price <= 0:
        return False
    change_pct = abs((current_price - reference_price) / reference_price) * 100.0
    return change_pct >= value
```

기존 `compute_target`/`is_fired`는 변경 없음(다른 기준 전용).

## 디스패처 — `app/services/alert/alert_dispatcher.py`

`evaluate_tick`의 알림 루프에서 REFERENCE 기준을 분기 처리. 기존 4기준은 현행 경로(1회성: 발동 시 `enabled=False`, `is_triggered=True`) 그대로 유지.

REFERENCE 처리 절차(자산 시세 `quote.price` 확보 후):
1. `alert.reference_price is None` → `alert.reference_price = quote.price` 설정·commit, 이번 tick 발동 안 함(`continue`).
2. `ref_fired(reference_price, quote.price, value)` 참 → 변동률 메시지 발송:
   - 발송 성공 시 `alert.reference_price = quote.price`로 **재설정**, `alert.last_notified_at = now`, `enabled`·`is_triggered` 미변경. commit.
   - 텔레그램 미설정 예외는 기존과 동일하게 처리(`return`).
3. 거짓 → 통과.

한 건 실패가 나머지를 막지 않는 기존 try/except·`asyncio.sleep(2)` rate-limit 패턴 유지.

## 메시지 — `app/services/alert/message.py`

- `_BASIS_LABEL["REFERENCE"] = "변동률 감시"`.
- REFERENCE 발동 메시지(트레일링): 종목명·"급격한 {상승|하락}!"·기준가·현재가·변동률(`+X.XX%`). 시장별 통화 단위(KR 원/그외 통화). 기존 `build_message`에 REFERENCE 분기 추가하거나 전용 빌더 분리(구현 시 결정, 기존 함수 시그니처 영향 없게).

## API / 검증 — `app/routers/alerts.py`

- `POST /api/alerts`: `basis="REFERENCE"` 허용. 입력 검증:
  - `direction` 미입력/임의값 → "BOTH"로 정규화.
  - `value > 0` 필수.
  - `reference_price`는 입력받지 않음(서버가 lazy-init).
- 기존 CRUD(GET/PUT/DELETE)·rearm 엔드포인트 재사용. REFERENCE는 `is_triggered`가 되지 않으므로 rearm 호출 대상이 아님(UI에서 재무장 버튼 미노출).

## 응답 스키마 / 뷰 — `app/services/alert/alert_store.py`

- 알림 행 뷰(`_alert_row` / `list_all_alerts_view` / 자산별 조회)가 응답에 **`reference_price`** 포함(REFERENCE가 아니면 NULL).
- REFERENCE 행의 `target_price`는 단일 목표가 개념이 없으므로 NULL 두고, 프론트가 `reference_price`+`value`로 밴드 표시.

## UI — 프론트엔드

### AlertForm (`frontend/src/components/AlertForm.tsx`)
- 기준 드롭다운에 "변동률 감시"(REFERENCE) 추가.
- REFERENCE 선택 시:
  - **방향 드롭다운 숨김**(BOTH 고정 전송).
  - value 입력 라벨/플레이스홀더 = "변동 %".

### 알림 허브(`Alerts.tsx`) / AssetDetail(`AssetDetail.tsx`) 테이블
- REFERENCE 행:
  - 방향 열 = `±{value}%`.
  - 목표가 열 = `reference_price` 있으면 `{reference_price.toLocaleString()} ±{value}%`, NULL이면 "산정 중".
  - 상태 = 항상 "활성"(끄기/켜기/삭제만, 재무장 없음).
- 기존 4기준 행 표시는 변경 없음(직전 커밋의 ABSOLUTE 방향 표시 수정 유지).

### 배지 / 집계
- 대시보드·관심종목 행 알림 개수 배지는 `enabled && !is_triggered`로 집계하므로 REFERENCE도 자동 포함(추가 작업 없음).

## 테스트 (TDD)

- **evaluator**: `ref_fired` — 상승 임계 도달/하락 임계 도달/임계 미만/경계값(==)/기준가 0 가드.
- **dispatcher**: lazy-init(reference NULL → 현재가 설정·미발동) / 발동 시 reference 재설정·enabled 유지·is_triggered 불변 / 임계 미만 미발동 / 기존 4기준 회귀(여전히 1회성).
- **store 뷰**: REFERENCE 행 응답에 reference_price 포함, 비REFERENCE는 NULL.
- **API**: REFERENCE 생성·검증(direction 기본 BOTH, value>0), 목록 조회.

기존 테스트는 invest_test 격리 스키마에서 실행:
`SCHEMA_NAME=invest_test TEST_DATABASE_URL='...' .venv/bin/pytest -q`.

## 알려진 minor (의도적 / 후속)

- manual 자산은 manual_price 고정이라 REFERENCE 사실상 미발동(무해, 기존 알림 패턴과 동일).
- reference 초기화가 첫 tick lazy-init이라 생성 직후~다음 tick(≤5분)까지 "산정 중" 표시.
- 변동률 알림은 자정/장종료 시 기준가 리셋 없음(트레일링 누적). 장중에만 평가되므로 갭은 다음 개장 첫 tick 변동으로 반영.

## 비목표 (YAGNI)

- 시간창 기반(N분/전일종가) 변동 감지(트레일링으로 대체).
- 변동률 알림 발송 이력/쿨다운(재설정 자체가 자연 쿨다운).
- 절대금액 기반 변동 임계(%만 지원).
- 텔레그램 외 채널.

## 참조

- 원본: `my_assistant` `app/services/bots/finance_bot.py` `check_price_alerts` (PERCENT_CHANGE).
- 기존 가격알림 설계: `docs/superpowers/specs/2026-06-18-price-alerts-design.md`.
- 관련 메모리: `holding-watchlist-ia-and-alerts` (REFERENCE 제외 결정).
