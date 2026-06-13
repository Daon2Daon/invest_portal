# invest_portal 1단계 설계: 기반 + 포트폴리오 코어

작성 기준일: 2026-06-13
대상 코드베이스: `/Users/mukymook/Library/CloudStorage/SynologyDrive-mookmuky/04.Coding/invest_portal`
참조 아키텍처: `ytdb` (스택·관례·디렉터리 구조)
기능 참조 출처: `my-assistant`의 `app/services/bots/finance_bot.py`, `chart_bot.py`

## 1. 목적과 범위

`my-assistant`에서 테스트 구현한 금융(finance)·차트(chartbot) 기능과 새로운 포트폴리오 관리 기능을
독립 프로젝트 `invest_portal`로 재구성하여 종합 자산관리 앱으로 발전시킨다. 본 문서는 **1단계
(기반 + 포트폴리오 코어)**의 설계만 다룬다.

궁극적으로는 `ytdb`와 통합해 하나의 로그인 베이스 포털앱(invest / work / personal 메뉴)으로
운영하며, ytdb의 자동 모니터링이 invest로 정보를 공급하는 구조를 지향한다. 본 1단계는 그 토대를
ytdb와 동일한 개발환경·스택으로 세운다.

### 1단계 범위 (이번 spec)

- 앱 골격(FastAPI / config / DB 부트스트랩 / 설정 체계)
- 자산 마스터 + **멀티마켓 티커 해석·시세 조회**(US / KR / JP / 가상화폐), ETF·채권 견고 대응
- 포트폴리오 CRUD(lot 단위) + 환율변환(기준통화 KRW) + 손익·비중 계산
- 포트폴리오 대시보드 / 보유 관리 / 자산 마스터 React SPA

### 명시적 비범위 (후속 단계)

- 2단계: chartbot(차트 생성 + AI 해석) 포팅, 텔레그램 발송, 스케줄 리포트
- 3단계: AI 포트폴리오 분석·리포트, 투자 저널(`portfolio_plans`), 위험신호·매수매도 도움,
  일별 자산추세 스냅샷
- 후속: 포털 로그인 베이스 통합, ytdb 모니터링 연동, work/personal 모듈
- 다중 사용자(멀티 테넌트). 본 1단계는 단일 운영자 기준
- 기존 테스트 DB(`agent_db`/`invest` 스키마)의 데이터 이관 — 폐기 후 신규 입력

## 2. 핵심 설계 결정

| 항목 | 결정 | 근거 |
|------|------|------|
| 스택 | ytdb와 동일(FastAPI + async SQLAlchemy 2.0 + asyncpg + PostgreSQL 전용) | 포털 통합 시 일원화. SQLite 미사용 |
| 아키텍처 수준 | ytdb의 스택·관례·디렉터리만 차용, **다중그룹 제어평면/`schema_translate_map` 제외**, 단일 `invest` 스키마 | 포트폴리오는 단일 사용자라 다중그룹 불필요 |
| DB 구축 | 사용자가 `.env`에 접속정보 입력 → 부팅 시 `ensure_schema()`가 스키마·테이블 멱등 생성 | ytdb의 부트스트랩 관례. 기존 데이터 무이관 |
| 기준통화 | KRW 고정(1단계). 환산: USD/KRW, JPY/KRW, 코인은 USD가격→KRW | 한국 사용자 기준 |
| 보유 모델 | **lot 단위 holdings**(매입 1건 = 1행). 손익·비중은 저장하지 않고 계산 | 매입날짜·평단·환차익 정확 산출 |
| 손익 분해 | 매입시점 환율(`purchase_fx_rate`) 보관 → 자산수익과 환차익 분리 | 환변동 자산의 손익 정확화 |
| 티커 조회 | **resolve-and-verify + 시장별 fallback 체인 + 수동 모드** | 기존 앱 최대 난관(ETF·채권·국가별)을 1급 기능으로 해결 |
| 프론트엔드 | React 18 + Vite + TS + Tailwind + react-router SPA, 백엔드는 JSON API | ytdb와 동일 스택, 포털 통합 용이 |
| 시세 데이터 소스 | yfinance(US·JP·crypto·지수) + pykrx(KR) + manual(채권·추적불가) | finance_bot의 검증된 소스. 무료 |
| 코드 이식 원칙 | 기존 코드를 복사하지 않고 검증된 로직·개념만 선별 참조해 새로 작성 | ytdb의 구현 원칙 계승 |

## 3. 디렉터리 구조

```
invest_portal/
├── app/
│   ├── main.py          FastAPI 진입점 + lifespan(ensure_schema)
│   ├── config.py        pydantic-settings: DATABASE_URL, FERNET_KEY
│   ├── db.py            async 엔진/세션/Base (단일 invest 스키마)
│   ├── bootstrap.py     ensure_schema: CREATE SCHEMA + 멱등 테이블 DDL
│   ├── models/          assets, exchange_rates, price_snapshots, holdings, app_settings
│   ├── schemas/         Pydantic 입출력
│   ├── services/
│   │   ├── market/      providers(yfinance, pykrx, manual) + registry + quote_service + resolver
│   │   ├── fx/          fx_service
│   │   ├── portfolio/   portfolio_service (가치평가·집계·비중·손익)
│   │   └── settings/    settings_manager (Fernet)
│   └── routers/         assets, holdings, portfolio, fx, settings
├── frontend/            React + Vite + TS + Tailwind SPA
├── requirements.txt
├── .env.example
└── docs/
```

## 4. 데이터 모델 (정규화 재설계, `invest` 스키마)

기존 비정규화 테이블(ticker/asset_name 중복, FK 없음, 매입날짜·비중 부재)을 대체한다.
모든 테이블은 `ensure_schema()`로 멱등 생성한다.

### 4.1 `assets` — 종목 마스터 (기존 `asset_currencies` 통합)

| 컬럼 | 타입 | 비고 |
|------|------|------|
| asset_id | BIGSERIAL PK | 대리키 |
| ticker | TEXT NOT NULL | 사용자 입력 티커(예: AAPL, 005930, 7203, BTC) |
| name | TEXT NOT NULL | 표시명(해석 시 자동 채움) |
| name_en | TEXT | |
| asset_type | TEXT NOT NULL | stock / etf / etn / index / crypto / bond / fund |
| market | TEXT NOT NULL | US / KR / JP / CRYPTO |
| currency | TEXT NOT NULL | USD / KRW / JPY |
| data_source | TEXT NOT NULL | yfinance / pykrx / manual |
| fetch_symbol | TEXT NOT NULL | 소스별 실제 조회 심볼(예: 005930, 7203.T, BTC-USD) |
| manual_price | NUMERIC | data_source=manual 시 사용자 입력 평가가/단가 |
| manual_price_currency | TEXT | manual_price의 통화 |
| manual_price_updated_at | TIMESTAMPTZ | manual_price 최종 갱신 시각 |
| is_active | BOOLEAN NOT NULL DEFAULT TRUE | |
| created_at / updated_at | TIMESTAMPTZ | |

제약: `UNIQUE(ticker, market)` — 동일 티커가 시장별로 충돌하지 않도록.

### 4.2 `exchange_rates` — 일별 환율

| 컬럼 | 타입 | 비고 |
|------|------|------|
| id | BIGSERIAL PK | |
| date | DATE NOT NULL | |
| base_currency | TEXT NOT NULL | 외화(USD/JPY) |
| quote_currency | TEXT NOT NULL | KRW |
| rate | NUMERIC NOT NULL | base 1단위당 quote 금액 (예: 1 USD = 1350 KRW) |
| source | TEXT | yfinance 등 |
| created_at | TIMESTAMPTZ | |

제약: `UNIQUE(date, base_currency, quote_currency)`. 1단계 보유 쌍: USD/KRW, JPY/KRW.

### 4.3 `price_snapshots` — 자산별 가격(최신/이력)

| 컬럼 | 타입 | 비고 |
|------|------|------|
| id | BIGSERIAL PK | |
| asset_id | BIGINT FK → assets | |
| date | DATE NOT NULL | |
| close | NUMERIC NOT NULL | 자산통화 기준 종가/현재가 |
| currency | TEXT NOT NULL | |
| source | TEXT | |
| created_at | TIMESTAMPTZ | |

제약: `UNIQUE(asset_id, date)`. `refresh` 시 당일 행 upsert.

### 4.4 `holdings` — 보유 포지션 (lot 단위)

매입 1건이 1행. 같은 종목 여러 번 매수 시 여러 lot이 생기고, 조회 시 종목별로 집계한다.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| holding_id | BIGSERIAL PK | |
| asset_id | BIGINT FK → assets NOT NULL | |
| purchase_date | DATE NOT NULL | 매입날짜 |
| quantity | NUMERIC NOT NULL | 수량 |
| purchase_price | NUMERIC NOT NULL | 자산통화 기준 매입단가 |
| purchase_fx_rate | NUMERIC | 매입시점 KRW 환율(자동 채움/nullable). KRW 자산은 1 |
| fee | NUMERIC DEFAULT 0 | 매입 수수료(선택) |
| memo | TEXT | |
| created_at / updated_at | TIMESTAMPTZ | |

### 4.5 `app_settings` — 런타임 설정

ytdb의 `app.settings` 관례를 단일 앱에 맞게 축소.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| setting_id | BIGSERIAL PK | |
| category | TEXT NOT NULL | general / market / notification(후속) / ai_gateway(후속) |
| key | TEXT NOT NULL | |
| value | TEXT | 평문 |
| value_enc | BYTEA | Fernet 암호화(is_secret=true 시) |
| value_type | TEXT NOT NULL DEFAULT 'string' | string/int/float/bool/json |
| is_secret | BOOLEAN NOT NULL DEFAULT FALSE | |
| updated_at | TIMESTAMPTZ | |

제약: `UNIQUE(category, key)`. 1단계 사용 키: `general.base_currency=KRW`,
`market.fx_pairs=["USD/KRW","JPY/KRW"]` 정도. 텔레그램/AI 키는 후속 단계용 자리.

> 손익평가·자산비중·일별 자산추세는 1단계에서 **저장하지 않고 계산**한다(holdings를 단일
> 진실원천으로). 추세 스냅샷 테이블은 3단계로 연기.

## 5. 멀티마켓 티커 해석 & 시세 (핵심)

기존 테스트 앱의 최대 난관(국가별 티커, 특히 ETF·채권 조회)을 1급 기능으로 해결한다.

### 5.1 기존 코드의 한계 (해결 대상)

- `finance_bot._get_kr_stock_quote`는 `stock.get_market_ohlcv_by_date`(주식 전용)만 호출 →
  **KR ETF는 `get_etf_ohlcv_by_date`가 필요한데 분기가 없어 조회 실패**, 불안정한 yfinance
  fallback으로 흘러감. (`_validate_kr_ticker`만 두 함수를 시도하는 불일치 존재)
- 개별 채권: 무료 API에 시세가 없어 조회 경로 자체가 부재.
- JP: quote 경로 미구현.
- 실패 시 무엇을 시도했고 왜 실패했는지 사용자에게 노출되지 않음.

### 5.2 통합 Provider 인터페이스

```
PriceProvider:
  resolve(ticker, market, asset_type_hint) -> ResolvedAsset | None
      # 이름·통화·유형·data_source·fetch_symbol 확정
  quote(asset)               -> Quote | None      # 최신가 + 등락(자산통화)
  history(asset, start, end) -> OHLCV | None       # 2단계 차트용 (인터페이스만)
```

구현체: `YFinanceProvider`(US·JP·crypto·지수), `PykrxProvider`(KR), `ManualProvider`(채권·추적불가).
`ProviderRegistry`가 `(market, data_source)`로 디스패치한다.

### 5.3 시장별 해석 체인

| 시장 | 해석 체인 | 유형 감지 |
|------|-----------|-----------|
| US | yfinance `SYM` | `info.quoteType` → EQUITY/ETF/INDEX/MUTUALFUND 등. 채권ETF(TLT·AGG) 정상 |
| JP | yfinance `SYM.T` | quoteType |
| KR | ① pykrx: `ticker ∈ get_etf_ticker_list()` → **ETF 함수**(`get_etf_ohlcv_by_date`, `get_etf_ticker_name`), `∈ get_etn_ticker_list()` → ETN, else 주식 함수 ② fallback yfinance `.KS`→`.KQ` | ETF/ETN/주식 리스트 멤버십(일별 캐시) |
| CRYPTO | yfinance `SYM-USD` | crypto |
| BOND(개별)·추적불가 | **수동 모드**(data_source=manual) | 사용자 지정 |

**핵심 버그 수정**: `PykrxProvider`가 ETF/ETN/주식을 **리스트 멤버십으로 먼저 판정**해 올바른
pykrx 함수를 선택한다. 이것이 기존 KR ETF 실패의 직접 해결책이다. ETF/ETN 티커 리스트는 일별
캐시한다.

### 5.4 수동 모드 (채권 등 추적불가 자산)

무료 API에 시세가 없는 개별 채권 등은 `data_source=manual`로 등록한다. 사용자가
`manual_price`(평가금액/단가)를 주기적으로 입력하고, 포트폴리오 평가는 이 값을 사용한다.
이로써 **어떤 자산이든 포트폴리오에 표현 가능**함을 보장한다.

### 5.5 resolve-and-verify UX

- `POST /api/assets/resolve {ticker, market, asset_type?}` → 저장 없이 **미리보기**
  (name, currency, current_price, data_source, fetch_symbol) 반환.
- 실패 시 **무엇을 시도했고 왜 실패했는지** 구조화된 응답(`tried: [...]`) + 수동 모드 제안.
- 프론트에서 미리보기 확인 후 `POST /api/assets`로 확정 저장. 해석 결과를 `assets`에 캐시한다.

### 5.6 견고성 (검증된 교훈 반영)

- 단일일이 아닌 **최근 ~7거래일 윈도우** 조회로 pykrx 데이터 지연/휴장 오판 회피.
- yfinance는 가격을 `history()`/`fast_info`로 취득(느리고 불안정한 `.info`는 메타데이터 한정),
  타임아웃 적용.
- **종목 1개 실패가 전체 집계를 깨지 않음** — 자산별 `price_status: ok / stale / error` 부여.
- NaN/Infinity는 JSON 직렬화 전에 None으로 정제.

## 6. 환율변환 & 손익 계산 (portfolio_service)

- `FxService`: USD/KRW, JPY/KRW를 yfinance에서 받아 `exchange_rates` upsert.
- KRW 환산 / 손익 분해:
  - 원가(KRW) = `quantity × purchase_price × purchase_fx_rate`
  - 현재가치(KRW) = `quantity × current_price × 현재환율`
  - 평가손익(KRW) = 현재가치 − 원가 / 손익률(%) = 평가손익 / 원가 × 100
  - 비중(%) = 종목 현재가치 / 전체 현재가치 × 100
- `purchase_fx_rate`는 매입일의 `exchange_rates`에서 자동 조회해 채우고, 없으면 현재 환율로
  대체(사용자 수정 가능). KRW 자산은 1.
- 종목별 집계: 같은 asset의 lot들을 합산해 총수량·가중평균 매입단가·총원가·현재가치·손익·비중 산출.

## 7. API (1단계)

- `assets`
  - `POST /api/assets/resolve` — 해석 미리보기(저장 안 함)
  - `POST/GET/PUT/DELETE /api/assets` — 자산 마스터 CRUD
  - `GET /api/assets/{id}/quote` — 실시간 시세
  - `PUT /api/assets/{id}/manual-price` — 수동 가격 갱신
- `holdings`
  - `POST/GET/PUT/DELETE /api/holdings` — lot CRUD
- `portfolio`
  - `GET /api/portfolio` — 종목별 집계(수량/평단/현재가/KRW가치/손익/손익%/비중) + 합계 요약
  - `POST /api/portfolio/refresh` — 시세·환율 갱신 + 스냅샷 upsert
- `fx`
  - `GET /api/fx`, `POST /api/fx/refresh`
- `settings`
  - `GET/PUT /api/settings` (최소)

응답은 NaN/Inf를 None으로 정제하고, 자산별 `price_status`를 포함한다.

## 8. 프론트엔드 (1단계, React SPA)

- **포트폴리오 대시보드**: 종목별 표(평단·현재가·평가손익·손익률·비중) + 총자산(KRW)·총손익
  요약 카드, 새로고침 버튼, `price_status` 뱃지.
- **보유 관리**: holding(lot) 추가/수정/삭제 폼(티커·시장·매입일·수량·단가·수수료·메모).
- **자산 마스터**: 티커+시장 입력 → resolve 미리보기 → 확정 등록. 수동 모드 자산은 평가가 입력
  UI 제공. 실패 시 `tried` 사유 표시.

## 9. 테스트 전략 (TDD)

- 단위: 환율변환·손익 분해, 종목별 집계, provider 심볼 매핑/유형 판정(yfinance·pykrx 모킹),
  KR ETF/ETN/주식 분기, NaN 정제.
- 통합: `ensure_schema()` 멱등성(반복 실행 무해), resolve→register→holdings→portfolio 흐름.
- 외부 API(yfinance/pykrx)는 모킹을 기본으로 하고, 실데이터 스모크 테스트는 선택적 마커로 분리.
- 스택: pytest + pytest-asyncio (ytdb와 동일).

## 10. 오류 처리

- provider 실패(네트워크·잘못된 티커)는 graceful 처리: 해석은 구조화된 실패 응답, 조회는 해당
  자산만 `price_status: error`로 표시하고 집계는 계속.
- 부팅 시 DB 접속 실패는 명확한 로그와 함께 기동 중단(부트스트랩 시크릿 문제 노출).
- Fernet 복호화 실패·설정 누락은 명시적 예외로 처리.
