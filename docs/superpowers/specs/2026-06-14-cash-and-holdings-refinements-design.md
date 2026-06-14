# invest_portal 1.5단계 설계: 현금 자산군 + 보유종목 등록 정비

작성 기준일: 2026-06-14
대상 코드베이스: `/Users/mukymook/Library/CloudStorage/SynologyDrive-mookmuky/04.Coding/invest_portal`
선행: 1단계(기반 + 포트폴리오 코어, main 병합 완료)

## 1. 목적과 범위

1단계에서 구현한 보유종목 관리를 실사용에 맞게 다듬고, **현금을 자산군으로 입력**할 수 있게 한다.
거래 원장(매도→실현손익, 배당)과 관심종목·액션 기능(차트/모니터링/리포트)은 다음 단계로 미룬다.

### 이번 범위
1. **현금 자산군** — 통화별·계좌별 현금 잔고를 입력하고 포트폴리오 총자산·비중에 포함.
2. **매입날짜 선택 입력** — 분할매수를 고려해 `purchase_date`를 선택값(nullable)으로.
3. **보유종목 등록 통합** — 자산 조회(resolve)→등록→보유 기록을 하나의 흐름/엔드포인트로.
4. **환율 모델 단순화** — 매수시점 환율(`purchase_fx_rate`) 제거. 원가는 자산 통화 기준, 표시·합계는 현재 환율로 KRW 환산.

### 비범위 (다음 단계, 방향만 기록)
- **거래 원장**(transactions: 매도→실현손익, 배당→수익) — holdings를 원장으로 진화. 원가법(평균/FIFO)은 그 사이클에서 결정.
- **관심종목(watchlist)** 등록 — `assets` 마스터를 공유, 2단계(모니터링과 짝).
- **액션 기능** — 차트생성·차트분석·변동 모니터링·리포트(2·3단계). 등록(데이터)과 액션(기능)은 별도 구현.
- **투자 저널**(정성 노트) — 별개 기능, 더 나중.

## 2. 아키텍처 맥락 (확정)

```
등록(registration)              액션(actions) — 등록된 자산에 수행
├─ 관심종목 (watchlist)  [다음] ─┐
└─ 보유종목 (holdings)   [현재] ─┴─▶ 차트생성·차트분석·변동 모니터링·리포트 [2·3단계]
```
- `assets` 마스터 테이블은 관심종목·보유종목이 **공유**한다(이번엔 보유종목만 사용).
- 등록(데이터 입력)과 액션(기능)은 분리된 관심사다. 액션은 등록된 자산을 참조한다.

## 3. 환율·손익 모델 단순화

매수 시점 환율을 보관하지 않는다. 모든 계산은 자산 통화 기준으로 하고, 표시·합계만 현재 환율로
KRW 환산한다.

종목별(자산 통화 = asset.currency):
- `cost_native   = quantity × purchase_price + fee`
- `value_native  = quantity × current_price`
- `pl_native     = value_native − cost_native`
- `pl_pct        = pl_native / cost_native × 100`

KRW 환산(현재 환율 `fx`, KRW는 1):
- `value_krw = value_native × fx`
- `cost_krw  = cost_native × fx`
- `pl_krw    = pl_native × fx`
- `weight_pct = value_krw / total_value_krw × 100`  (total은 현금 포함)

귀결(설계 의도): 원금에 대한 **환차익은 별도 손익으로 분리되지 않는다**(원가도 현재 환율로 환산).
손익은 자산 가격 변동(통화 기준)만 반영한다. 이는 "해외 자산의 과거가치 산정 불필요" 요구의
자연스러운 결과이며 모델을 단순화한다.

### 모델 변경
- `holdings.purchase_fx_rate` **컬럼 제거**.
- `holdings.purchase_date` → **nullable**(선택 입력). 어떤 계산에도 쓰이지 않고 기록용.
- `fee`는 자산 통화 기준으로 원가에 합산(기존 유지).

> 마이그레이션: `ensure_schema()`는 생성 전용(create_all)이라 기존 테이블을 변경하지 않는다.
> 현재 `invest` 스키마의 holdings/관련 테이블은 비어 있으므로(실데이터 없음), 구현 시 영향 받는
> 테이블(holdings 등)을 drop 후 재부트스트랩하면 새 구조로 생성된다. 운영 데이터가 없을 때만
> 유효한 단순 접근이며, 거래 원장 도입 사이클부터는 정식 마이그레이션 절차를 둔다.

## 4. 현금 자산군

### 4.1 데이터 — 새 테이블 `cash_balances`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| id | BIGSERIAL PK | |
| currency | TEXT NOT NULL | KRW / USD / JPY 등 |
| amount | NUMERIC NOT NULL | 금액(해당 통화) |
| label | TEXT | 선택: "증권사 예수금", "은행" 등 계좌 구분 |
| memo | TEXT | 선택 |
| created_at / updated_at | TIMESTAMPTZ | |

통화별·계좌별로 여러 행 허용(독립 관리). 매수·매도와 연동하지 않는다(사용자가 직접 입력·수정).

### 4.2 평가·통합 (portfolio_service)
- 현금 KRW 환산 = `amount × fx(currency→KRW)` (KRW는 ×1).
- **총자산·자산비중에 현금 포함**. 포트폴리오 응답에 `cash` 목록 추가:
  `[{id, currency, amount, label, value_krw, weight_pct}]`.
- `summary.total_value_krw`는 종목 평가액 + 현금 합계. `weight_pct`(종목·현금)는 이 총액 기준.

### 4.3 API
- `GET /api/cash` — 목록
- `POST /api/cash` — 추가 `{currency, amount, label?, memo?}`
- `PUT /api/cash/{id}` — 수정
- `DELETE /api/cash/{id}` — 삭제

## 5. 보유종목 등록 통합

자산 조회→등록→보유 기록을 한 흐름으로 묶는다. `assets` 마스터는 그대로 유지(관심종목이 추후
재사용). 테이블 통합이 아니라 입력 UX·엔드포인트 통합이다.

### 5.1 통합 엔드포인트
`POST /api/holdings/with-asset` — 한 번에 자산 upsert + 보유 생성.
- 입력: resolve로 확정된 자산 필드(ticker, market, asset_type, currency, data_source, fetch_symbol,
  name, name_en?) + 보유 필드(quantity, purchase_price, purchase_date?, fee?, memo?).
- 동작: `(ticker, market)`로 자산을 찾고 없으면 생성(upsert), 그 asset_id로 holding 생성. 트랜잭션 1건.
- 기존 `POST /api/assets`, `POST /api/holdings`(asset_id 기반)는 유지(자산 마스터 관리·기존 자산에
  추가 매수용).

### 5.2 UI — "보유종목 추가" 단일 폼
1. 티커·시장·유형 입력 → **조회(resolve)** 미리보기(이름·통화·현재가·source)
2. 미리보기 확인 후 수량·매입단가·(매입일 선택)·수수료·메모 입력
3. **추가** → `with-asset`로 자산+보유 한 번에 생성
- 기존 자산에 분할매수: 자산 목록에서 선택해 보유만 추가하는 경로도 제공(드롭다운).
- 매입일은 비워도 등록 가능(placeholder, 선택).

기존 분리 화면 정리:
- 보유 추가는 위 통합 폼으로 일원화.
- 자산 마스터 목록 화면은 "등록된 종목 관리"로 남김(향후 관심종목 토대).

## 6. 영향 받는 컴포넌트
- `app/models/holding.py` — purchase_fx_rate 제거, purchase_date nullable.
- `app/models/cash_balance.py` — 신규.
- `app/models/__init__.py`, `app/bootstrap.py` — 신규 모델 등록.
- `app/services/portfolio/portfolio_service.py` — 손익식 단순화(현재 환율), 현금 합산·비중.
- `app/services/fx/fx_service.py` — 변경 없음(현재 환율 조회 그대로).
- `app/routers/holdings.py` — purchase_fx_rate 자동채움 로직 제거, `with-asset` 추가.
- `app/routers/cash.py` — 신규.
- `app/schemas/` — holding(날짜 선택, fx_rate 제거), cash, portfolio(cash 추가) 스키마.
- `app/main.py` — cash 라우터 등록.
- `frontend/src/pages/Holdings.tsx` — 통합 폼(resolve 포함), 날짜 선택.
- `frontend/src/pages/Cash.tsx`(신규), `Dashboard.tsx`(현금 섹션), `App.tsx`(라우트), `api.ts`(cash·with-asset).

## 7. 테스트 전략 (TDD)
- 단위: 손익 단순화식(자산통화 기준 + 현재 환율 환산), 현금 KRW 환산·비중, 총액에 현금 포함.
- 통합(TEST_DATABASE_URL/격리 스키마): cash CRUD, `with-asset` upsert(신규/기존 자산), 날짜 없는 holding 생성.
- 기존 provider/resolver 테스트는 영향 없음(회귀 확인).

## 8. 오류 처리
- `with-asset`: 자산 upsert 중복은 정상 처리(기존 asset_id 사용). 잘못된 통화/금액은 422.
- 현금 amount 음수 허용 여부: 음수 금지(검증). 환율 미존재 통화는 KRW 환산 0 + 경고 표시(기존 price_status 패턴 준용).
