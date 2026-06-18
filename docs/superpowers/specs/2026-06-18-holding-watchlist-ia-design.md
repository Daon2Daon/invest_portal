# 보유/관심 정보구조(IA) + 자산 상세 허브 — 설계 (spec A)

작성일: 2026-06-18
단계: 3단계 진입을 위한 정보구조 재정비. 선행: 1단계(포트폴리오 코어), 2단계(차트·텔레그램·AI분석·스케줄 자동발송) — 모두 main 병합 완료.
후속: **스펙 B(가격 알림)** 가 본 스펙에서 만든 자산 상세 허브에 "알림" 탭을 추가. 이후 다른 자산별 기능(리포트·위험신호)도 같은 허브로 편입.

## 목적

앱을 **투자·재테크·자산관리** 목적에 맞게 최상위 정보구조를 정리한다.

- 자산을 **보유(포트폴리오) / 관심종목** 두 갈래로 나눠 본다.
- 보유 자산은 **포트폴리오 관점(대시보드)** 으로, 관심종목은 **추적 리스트** 로 본다.
- 가격 모니터링·차트·AI 분석 등 **세부 기능은 보유/관심 구분 없이 자산별 하위기능**으로, 자산 상세 화면(허브) 한 곳에 모은다.

본 스펙은 **화면 골격(IA)과 진입 동선**만 만든다. 새 도메인 기능(가격 알림)은 스펙 B에서 다룬다.
차트·AI분석·스케줄의 **로직은 변경하지 않고 UI 위치만 허브로 이동**한다.

## 확정된 결정

- **분류는 파생(derived).** 자산에 별도 분류 필드를 두지 않는다.
  - **보유** = 해당 자산에 holding lot 행이 1개 이상.
  - **관심종목** = 활성(`is_active=True`) 자산이지만 holding lot이 0개.
  - 매도는 별도 트랜잭션이 아니라 lot 삭제/수량 조정으로 표현한다. lot이 0개가 되면 자동으로 관심종목으로 복귀한다. (현재 데이터 모델·`portfolio_service` 동작과 일치)
- **가격 알림은 보유/관심 공통 기능**이다(스펙 B). 분류는 화면 구성의 문제일 뿐, 자산별 기능은 분류와 무관하게 동작한다.
- **명칭**: 보유 측은 "포트폴리오", 관심 측은 "관심종목"으로 표기한다.
- **자산 상세 허브는 라우트 진입**(`/asset/:id`)이며 상위 네비 메뉴에 두지 않는다. 포트폴리오/관심종목 목록에서 자산을 클릭해 들어간다.
- **신규 테이블·마이그레이션 없음.** 백엔드는 조회 엔드포인트 2개만 추가한다.

## 아키텍처

### 분류 판정 (백엔드 공유 헬퍼)

`app/services/portfolio/` 에 보유 여부 판정을 공유 함수로 둔다(라우터·watchlist 서비스가 공유).

```python
async def held_asset_ids(db) -> set[int]:
    """holding lot 행이 1개 이상 존재하는 asset_id 집합."""
```

- 구현: `select(Holding.asset_id).distinct()` 결과 집합.
- 보유/관심 판정은 이 집합 멤버십으로 한다(자산별 개별 쿼리 회피).

### 신규 엔드포인트 1 — `GET /api/watchlist`

관심종목(보유 lot 없는 활성 자산) 목록 + 라이브 시세를 반환한다. `portfolio()` 패턴을 따른다.

```json
[
  {
    "asset_id": 12, "ticker": "TSLA", "name": "Tesla", "market": "US",
    "currency": "USD", "asset_type": "stock", "asset_class": "주식",
    "current_price": 251.3, "change": 3.2, "change_pct": 1.29,
    "price_status": "ok"
  }
]
```

- 구현: 활성 자산 중 `held_asset_ids`에 없는 자산을 모아 각 자산에 `get_quote(asset)`. manual 자산은 `manual_price` 기준이며 `change/change_pct`가 없으면 `null`.
- 위치: `app/services/portfolio/watchlist_service.py`(`get_watchlist(db)`), 라우터 `app/routers/watchlist.py`(`GET /api/watchlist`).

### 신규 엔드포인트 2 — `GET /api/assets/{id}/detail`

자산 상세 허브 헤더용 집계. 보유/관심 모두에서 동일 형태로 응답한다.

```json
{
  "asset": { /* AssetOut */ },
  "held": true,
  "holding_summary": {
    "quantity": 10, "avg_price": 220.5,
    "value_krw": 3400000, "profit_loss_krw": 120000, "profit_loss_pct": 3.7
  },
  "quote": { "price": 251.3, "currency": "USD", "change_pct": 1.29, "status": "ok" }
}
```

- `held=false`면 `holding_summary=null`.
- 보유 집계는 기존 `portfolio_service.aggregate_position`을 재사용(해당 자산의 lot만 모아 현재가·환율로 산출).
- 위치: `app/routers/assets.py`에 `GET /api/assets/{id}/detail` 추가.

기존 엔드포인트(`/api/assets`, `/api/portfolio`, `/api/charts/*`, `/api/settings/*` 등)는 변경하지 않는다.

### 프론트엔드 — 내비게이션 재편 (`App.tsx`)

| 경로 | 메뉴 | 내용 |
|------|------|------|
| `/` | 포트폴리오 | 보유 포트폴리오(기존 `Dashboard`). 종목 행 클릭 → `/asset/:id` |
| `/watchlist` | 관심종목 | 신규 `Watchlist` 페이지. 목록 + 추가. 행 클릭 → `/asset/:id` |
| `/manage` | 관리 | 기존 `Holdings`(보유·현금 추가/수정) |
| `/asset/:id` | (네비 없음) | 신규 `AssetDetail` 허브. 자산 클릭 시 진입 |
| `/settings` | 설정 | 기존 `Settings` |

- 기존 상위 네비 "차트"는 제거되고 차트 기능은 자산 상세 허브로 흡수된다.
- `react-router-dom`(v7, 이미 사용 중)의 `useParams`/`Link`/`useNavigate`로 동선 구현.

### 프론트엔드 — 관심종목 페이지 (`pages/Watchlist.tsx`)

- **목록 테이블**: 종목(name·ticker·market) · 현재가 · 변화율(`change_pct`, 색상) · 자산군 · 액션(삭제). 행 클릭 → `/asset/:id`.
- **관심종목 추가**: 티커 + 시장 + 유형 입력 → `api.resolve`(미리보기) → "관심 추가" → `POST /api/assets`(lot 없이 자산만 생성). `Holdings.tsx`의 resolve 미리보기 UI 패턴 재사용.
- **삭제**: `DELETE /api/assets/{id}`. 관심종목은 lot이 없어 FK 충돌이 없다.
- 시세 상태가 `ok`가 아니면 변화율 칸에 경고 표시(`⚠`), Dashboard의 `price_status` 표기와 일관.

### 프론트엔드 — 자산 상세 허브 (`pages/AssetDetail.tsx`)

`Charts.tsx`를 일반화한다(드롭다운 선택 제거, 라우트 파라미터로 자산 결정).

- **선택**: `useParams()`의 `:id`로 자산 결정. (기존 Charts의 자산 드롭다운 제거)
- **헤더**(`GET /api/assets/{id}/detail`):
  - 종목명(티커·시장) · **보유/관심 뱃지** · 현재가 + 변화율
  - 보유면 추가로 수량 · 평단 · 평가손익(KRW, %)
- **섹션(기존 기능 그대로 이전)**:
  - 일봉 / 주봉 차트(`/api/charts/{id}?period=`)
  - AI 분석(`POST /api/charts/{id}/analyze`)
  - 텔레그램 발송(`POST /api/charts/{id}/send-telegram`)
  - 자동발송 스케줄(`GET/PUT/DELETE /api/charts/{id}/schedule`)
- **알림 탭 자리**: 스펙 B에서 "가격 알림" 섹션이 이 허브에 추가된다. 본 스펙에서는 자리만 비워둔다(빈 섹션·플레이스홀더도 만들지 않음 — 구조만 허브로 정리).
- 기존 `pages/Charts.tsx`는 `AssetDetail.tsx`로 대체되어 삭제한다.

### 프론트엔드 — `api.ts` 추가

```ts
listWatchlist()                          // GET /api/watchlist
createWatchlistAsset(resolvedAsset)      // POST /api/assets  (lot 없음)
assetDetail(id)                          // GET /api/assets/{id}/detail
deleteAsset(id)                          // DELETE /api/assets/{id}
```

- 기존 chart/schedule/analyze 함수는 `AssetDetail`가 계속 사용한다.
- `WatchlistItem`, `AssetDetail` TS 인터페이스 추가.

## 데이터 흐름

```
포트폴리오(/)        ──클릭──┐
                            ├──> /asset/:id (AssetDetail 허브)
관심종목(/watchlist) ──클릭──┘        │
                                     ├─ GET /api/assets/{id}/detail (헤더)
                                     ├─ GET /api/charts/{id}?period=… (차트)
                                     ├─ POST /api/charts/{id}/analyze (AI)
                                     ├─ POST /api/charts/{id}/send-telegram
                                     └─ GET/PUT/DELETE /api/charts/{id}/schedule
관리(/manage)  ── 보유 추가 → POST /api/holdings/with-asset
관심종목 추가 → POST /api/assets (lot 없음)
```

## 에러 처리

- `GET /api/watchlist`: 자산별 시세 조회 실패는 해당 항목 `price_status="error"`로 표기하고 목록에서 제외하지 않는다(자산은 등록돼 있으므로 보여줘야 한다).
- `GET /api/assets/{id}/detail`: 자산 없음 404. 시세 실패는 `quote.status="error"`로 전달(허브는 차트/기능을 계속 노출).
- 관심종목 추가 시 중복 티커/시장은 기존 `POST /api/assets`의 409를 UI에 표시.
- 프론트는 기존 `j<T>` 래퍼의 throw를 캐치해 폼/행에 에러 텍스트 표시.

## 테스트 계획

현재 앱의 단위테스트 관례(서비스·라우터 단위)를 따른다.

- `test_watchlist.py`
  - 보유 lot 있는 자산은 관심 목록에서 제외, lot 없는 활성 자산만 포함.
  - manual 자산은 `manual_price` 기준으로 포함되며 `change_pct=null` 허용.
  - 비활성(`is_active=False`) 자산 제외.
- `test_assets_detail.py`
  - 보유 자산: `held=true` + `holding_summary` 수량·평단·손익 산출(`aggregate_position` 일관).
  - 관심 자산: `held=false` + `holding_summary=null`.
  - 없는 자산: 404.
- `held_asset_ids` 헬퍼: lot 유무에 따른 집합 멤버십 단위 검증.
- 프론트: 자동화 테스트 인프라가 없으므로 `tsc`/빌드 통과 + 수동 스모크(포트폴리오→상세, 관심종목 추가→상세, 차트/분석/발송/스케줄 동작 확인). API 계약은 위 백엔드 테스트가 보증.

## 비목표 (명시)

- **가격 알림** — 스펙 B에서 본 허브에 추가.
- **명시적 분류 필드** — 파생 판정으로 충분(YAGNI).
- **차트/AI분석/스케줄 로직 변경** — UI 위치만 허브로 이동, 동작·엔드포인트 불변.
- **매도(거래) 트랜잭션 모델** — 현행대로 lot 편집으로 처리.
- **인증·다중 사용자** — 단일 사용자 전제 유지.

## 영향 받는 파일 (요약)

신규
- `app/services/portfolio/watchlist_service.py`
- `app/routers/watchlist.py`
- `frontend/src/pages/Watchlist.tsx`
- `frontend/src/pages/AssetDetail.tsx`
- `tests/test_watchlist.py`, `tests/test_assets_detail.py`

수정
- `app/services/portfolio/portfolio_service.py` (또는 인접 모듈) — `held_asset_ids` 헬퍼 추가
- `app/routers/assets.py` — `GET /api/assets/{id}/detail` 추가
- `app/main.py` — watchlist 라우터 등록
- `frontend/src/App.tsx` — 라우트/네비 재편
- `frontend/src/api.ts` — 함수·타입 추가

삭제
- `frontend/src/pages/Charts.tsx` (→ `AssetDetail.tsx`로 대체)
