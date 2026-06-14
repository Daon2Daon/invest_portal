# invest_portal 설계: 자산군 분류 + 자산군별 비중

작성 기준일: 2026-06-14
대상 코드베이스: `/Users/mukymook/Library/CloudStorage/SynologyDrive-mookmuky/04.Coding/invest_portal`
선행: 1단계(코어), 1.5단계(현금+등록정비), UI 간소화, KR ETF 폴백 수정 — 모두 main 병합 완료

## 1. 목적과 범위

보유 자산을 **자산군(asset class)** 으로 분류하고, 대시보드에서 **자산군별 비중**을 보여준다.
기존 `asset_type`(stock/etf/bond/…, 자동 감지된 상품 유형)은 채권ETF·주식ETF를 구분하지 못하므로,
사용자가 지정하는 별도의 단일 자산군 필드를 둔다.

### 이번 범위
1. `assets.asset_class`(단일, 사용자 지정) 추가 — 추천 목록 + 자유 입력.
2. 등록 시 `asset_type`에서 기본 자산군 자동 채움, 사용자 수정 가능.
3. 자산 수정 엔드포인트(`PUT /api/assets/{id}`)로 asset_class·name 수정.
4. 대시보드 **자산군별 비중** 집계·표시(현금은 "현금성" 자산군으로 자동 포함).

### 비범위 (추후)
- 다중 태그(한 자산이 여러 군). 본 설계는 자산당 단일 자산군(비중 합 100% 보장).
- 자산군별 목표비중·리밸런싱 제안.
- 파이차트 등 시각화(이번엔 표). 거래 원장/실현손익/배당(별도 단계).

## 2. 자산군 값

추천 목록(프론트 datalist, 자유 입력 허용):
**주식 · 채권 · 현금성 · 원자재 · 가상자산 · 대체투자 · 기타**

`asset_type` → 기본 자산군 매핑(`default_asset_class`):

| asset_type | 기본 asset_class |
|------------|------------------|
| stock, etf, fund, index | 주식 |
| bond | 채권 |
| crypto | 가상자산 |
| commodity | 원자재 |
| etn, 그 외/None | 기타 |

ETF 기본값은 "주식"이며, 채권ETF 등은 사용자가 "채권"으로 변경한다(채권ETF 분류가 이 기능의 핵심 동기).
현금(`cash_balances`)은 자산이 아니라 별도지만, 비중 집계에서 자산군 **"현금성"** 으로 자동 분류한다.

## 3. 데이터 모델

`assets`에 컬럼 추가:

| 컬럼 | 타입 | 비고 |
|------|------|------|
| asset_class | TEXT (nullable) | 사용자 지정 단일 자산군. NULL이면 집계 시 "기타"로 취급 |

마이그레이션: `ensure_schema()`는 생성 전용이라 기존 `assets` 테이블에 컬럼을 추가하지 못한다.
개발 DB는 `ALTER TABLE invest.assets ADD COLUMN IF NOT EXISTS asset_class TEXT`(비파괴)로 추가하고,
기존 자산 행은 `asset_type` 기준 `default_asset_class`로 backfill한다(실데이터 보존).

## 4. 백엔드

### 4.1 default_asset_class
`app/services/market/resolver.py`(또는 인접 모듈)에 순수 함수 `default_asset_class(asset_type: str | None) -> str` 정의(위 매핑). 단위 테스트 대상.

### 4.2 ResolvedAsset / resolve
- `ResolvedAsset` 데이터클래스에 `asset_class: str | None = None` 추가.
- `AssetResolver.resolve`는 성공 자산을 반환하기 직전, (유형 hint 오버라이드까지 반영된) `asset.asset_type` 기준으로 `asset.asset_class = default_asset_class(asset.asset_type)`를 채운다.
- 채권(hint=bond)·수동 경로도 동일하게 기본 자산군이 채워지도록 한다(manual provider 자산도 default 적용).

### 4.3 스키마
- `ResolvedAssetOut`: `asset_class` 추가(미리보기 표시).
- `AssetCreate`·`HoldingWithAssetCreate`: `asset_class: str | None = None` 추가.
- `AssetOut`: `asset_class` 추가.
- 신규 `AssetUpdate { asset_class?: str, name?: str }`.
- `Position`(portfolio): `asset_class: str` 추가(없으면 "기타").
- `AllocationSlice { asset_class: str, value_krw: float, weight_pct: float }`.
- `PortfolioOut`: `allocation: list[AllocationSlice]` 추가.

### 4.4 라우터
- `assets` 라우터: `PUT /api/assets/{id}` 추가 — `AssetUpdate` 부분 갱신(asset_class, name). 404 처리.
- `holdings`/`with-asset`: 자산 신규 생성 시 `asset_class` 저장(body에 있으면 사용, 없으면 `default_asset_class(asset_type)`).

### 4.5 get_portfolio 집계
- 각 position dict에 `asset_class = asset.asset_class or "기타"` 포함.
- 비중 집계: positions를 asset_class로 그룹 합산 + 현금 전체를 "현금성"으로 합산.
  `allocation = [{asset_class, value_krw, weight_pct}]`, weight = class_value / total_value(현금 포함) × 100, 평가액 desc 정렬.
- `total_value`/기존 summary는 변경 없음.

## 5. 프론트엔드

- `api.ts`: `Position`에 `asset_class`, `PortfolioOut`에 `allocation`, 신규 `updateAsset(id, {asset_class?, name?})`. `ASSET_CLASSES` 추천 상수.
- **보유종목 추가**(Holdings): resolve 미리보기에 자산군 입력(`<input list=datalist>` 추천값, 기본값 = `preview.asset.asset_class`). with-asset payload에 `asset_class` 포함.
- **보유 목록**(Holdings): 자산군 컬럼 표시. 인라인 수정 시 `updateAsset(asset_id, {asset_class})` 호출(자산 단위 — 같은 자산의 모든 lot에 반영). 자산명도 함께 표시(기존).
- **대시보드**: 포지션 표에 자산군 컬럼 추가 + 별도 **"자산군별 비중" 표**(자산군 / 평가액(KRW) / 비중) — `portfolio.allocation` 렌더.

## 6. 테스트
- 단위: `default_asset_class` 매핑(각 유형 + None), allocation 집계(positions+현금=현금성, 비중 합 ≈100%, NULL→기타).
- 통합/스모크(실DB): 마이그레이션(컬럼 추가+backfill), with-asset 시 asset_class 저장, `PUT /api/assets/{id}` 수정, `GET /api/portfolio`의 allocation. 외부 시세 API는 단위테스트에서 모킹.
- 회귀: 기존 provider/resolver/portfolio 테스트 유지(ResolvedAsset 필드 추가·Position 필드 추가 반영).

## 7. 오류 처리
- `PUT /api/assets/{id}` 미존재 → 404. asset_class 빈 문자열 입력 시 NULL 또는 그대로 저장(집계는 "기타" 처리) — 빈 문자열은 None으로 정규화.
- allocation에서 total_value 0이면 비중 0(기존 패턴과 동일한 방어).
