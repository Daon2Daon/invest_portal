# 알림 허브 + 디자인 시스템 통합 — 설계

작성일: 2026-06-20

테스트 결과 드러난 두 문제를 해결한다.

1. **알림 가시성** — 알림은 종목 상세에서 편하게 설정하지만, 어떤 종목에 어떤 알림이 걸려 있는지 한눈에 볼 방법이 없다.
2. **투박한 디자인** — 페이지가 기본 Tailwind 유틸(회색 테두리+파랑/빨강)만 쓰고, `index.css`에는 Vite 템플릿 잔재가 남아 실제 페이지와 충돌한다.

두 작업은 신규 '알림' 페이지가 새 디자인 위에서 만들어지고, 알림 배지가 재단장 대상 페이지에 들어가므로 하나의 spec으로 묶되, 구현은 **디자인 토대 → 기존 페이지 재단장 → 알림 허브 신규 구축** 순으로 진행한다.

---

## Part A — 알림 허브 (전용 '알림' 메뉴)

### 백엔드

- `GET /api/alerts`의 `asset_id` 쿼리 파라미터를 **선택값**으로 변경한다.
  - `asset_id` 있음 → 기존 `list_alerts_view(db, asset_id)` 그대로(상세 페이지 호환).
  - `asset_id` 없음 → 신규 `alert_store.list_all_alerts_view(db)`로 전체 알림 반환.
- `alert_store.list_all_alerts_view(db)`:
  - 활성 자산(`Asset.is_active`)의 모든 알림을 자산과 조인해 모은다(enabled/triggered 무관 — 전체를 보여줘야 함).
  - **자산당 시세 1회만 조회**: alert를 `asset_id`로 그룹핑하고, 각 자산에 대해 `get_quote`를 한 번 호출한 뒤 그 자산의 알림들을 계산한다(알림이 많아도 quote 호출은 종목 수만큼).
  - 자산별 계산은 기존 `list_alerts_view`의 항목 로직(`resolve_basis_price` → `compute_target` → `is_fired`)을 공유하도록 헬퍼로 추출해 재사용한다.
  - 각 항목은 기존 라이브 필드(`alert_id, asset_id, basis, direction, value, enabled, is_triggered, note, target_price, current_price, price_status, fired`)에 **자산 메타(`asset_name`, `ticker`, `market`, `asset_class`)**를 추가한다.
  - 정렬: 발동된 것(`fired`/`is_triggered`)을 위로, 그다음 종목명.
- 생성/수정/삭제/재무장은 **기존 엔드포인트를 그대로 재사용**한다(`POST /api/alerts`, `PUT /api/alerts/{id}`, `POST /api/alerts/{id}/rearm`, `DELETE /api/alerts/{id}`). 신규 백엔드 코드는 목록 조회 경로 하나뿐.

### 프론트

- 신규 `pages/Alerts.tsx`. 네비에 '알림' 추가 → **포트폴리오 · 관심종목 · 알림 · 관리 · 설정**.
- **목록**: 종목명(+ticker·market), 기준(절대가/평균매입가/52주 고·저), 방향(이상/이하), 목표가, 현재가, 발동상태. 행에서 인라인 조작:
  - 켜기/끄기(`PUT {enabled}`), 삭제(`DELETE`), 발동된 알림 재무장(`POST .../rearm`).
- **"알림 추가" 폼**(페이지 상단): 종목 선택 드롭다운(보유+관심 자산 목록) → 기준/방향/값 입력 → `POST /api/alerts`.
  - 기준 옵션은 종목 성격에 따라 제한: 평균매입가(PURCHASE_AVG)=보유 종목만, 52주(WEEK52_*)=비-manual 자산만. 서버도 422로 막지만 UI에서도 비활성 처리.
  - 이 폼/검증 로직은 `AssetDetail.tsx`의 기존 알림 폼에서 **공용 컴포넌트(`AlertForm`)로 추출**해 양쪽이 공유한다(자산 선택 유무만 차이).
  - 종목 후보 목록은 기존 `GET /api/portfolio`(보유) + `GET /api/watchlist`(관심)로 구성.
- **알림 개수 배지**: 포트폴리오/관심종목 목록의 각 행에 활성 알림 수 pill 표시. 전체 알림 목록을 한 번 받아 `asset_id`별 카운트로 매핑. 배지 클릭 시 알림 페이지로 이동.

---

## Part B — 디자인 시스템 통합 (라이트/다크 + 반응형)

### 디자인 토큰

- `index.css`의 Vite 템플릿 잔재 제거: `#root { width:1126px; text-align:center; ... }`, `h1 { font-size:56px }`, `code`/`.counter`/`#social` 등 앱과 무관한 규칙.
- CSS 변수 토큰 체계 정의(라이트/다크 두 세트):
  - 표면: `--bg`(페이지), `--surface`(카드/패널), `--surface-2`(강조 카드), `--border`.
  - 텍스트: `--text`, `--text-muted`.
  - 포인트: `--accent`(보라, 단일 토큰 — 나중에 한 줄로 교체 가능), `--accent-fg`(포인트 위 글자).
  - 손익: `--up`(빨강=상승), `--down`(파랑=하락). 한국 관례 유지.
- 다크/라이트 전환은 `<html data-theme="light|dark">`에 토큰 세트를 매핑.

### 테마 토글

- 기본값은 시스템 설정(`prefers-color-scheme`)을 따른다.
- 사용자가 토글하면 `localStorage`('theme')에 저장하고 이후 그 값을 우선한다.
- 앱 부팅 시 저장값(없으면 시스템값)으로 `<html data-theme>`를 설정하는 작은 초기화 로직.
- 토글 버튼은 네비(셸)에 배치.

### 반응형 네비 셸

- 신규 레이아웃 컴포넌트(`components/AppShell.tsx`)가 `App.tsx`의 인라인 `<nav>`를 대체한다.
- `lg`(~1024px) 이상 = 좌측 **사이드바**(세로 메뉴), 미만 = 상단 **탭바**(가로 메뉴). Tailwind 반응형 클래스로 처리(JS 분기 최소화).
- 콘텐츠 영역은 사이드바 옆(넓은 화면) / 탭바 아래(좁은 화면)에 배치. 라우팅은 기존 `react-router-dom` 구조 유지.

### 컴포넌트 정리

- 반복 UI(카드, 표, 버튼, 배지/pill, 폼 입력)를 토큰 기반 공용 스타일로 통일한다. 소수의 작은 공용 컴포넌트 또는 일관된 Tailwind 클래스 묶음으로 구성(과한 추상화는 지양).
- 기존 5개 페이지(Dashboard, Holdings, Watchlist, AssetDetail, Settings) + 신규 Alerts 페이지를 모두 새 시스템으로 재단장.
- 손익 빨강/파랑, 가격 경고(⚠) 등 의미 색은 토큰으로 유지.

---

## 구현 순서

1. **디자인 토대**: 토큰 정리(index.css) + 테마 토글 + `AppShell` 반응형 셸.
2. **기존 페이지 재단장**: Dashboard/Holdings/Watchlist/AssetDetail/Settings를 새 토큰·컴포넌트로.
3. **알림 허브**: 백엔드 `list_all_alerts_view` + `GET /api/alerts` 선택 파라미터화 → `AlertForm` 공용 추출 → `Alerts.tsx` 신규 → 배지.

토대를 먼저 깔아야 알림 페이지를 처음부터 새 스타일로 만든다.

## 테스트

- **백엔드**: `list_all_alerts_view` 단위테스트(빈 경우 / 다종목 그룹 / 라이브 계산값 / 자산당 quote 1회) + 라우터 테스트(`asset_id` 없는 경우 전체 반환, 있는 경우 기존 동작 유지). invest_test 격리 스키마.
- **프론트**: `npm run build` 통과 + 실DB 스모크(알림 목록·생성·켜기끄기·삭제·재무장, 배지 카운트).
- **수동 확인**: 테마 토글(라이트↔다크, 새로고침 후 유지), 반응형 네비(창 너비 변경 시 사이드바↔탭바 전환).

## 범위 제외 (YAGNI)

- 알림 발송 이력 페이지.
- 종목 검색 자동완성(별도 후순위 로드맵 항목).
- 커스텀 테마 색상 선택 UI(포인트색은 코드 토큰 교체로 충분).
- matplotlib 차트 PNG의 다크모드 대응(별개 영역).
- 알림 페이지에서의 알림 수정(값/방향 변경)은 인라인 토글·삭제·재무장으로 충분 — 값 변경은 삭제 후 재생성 또는 상세 페이지에서. (`PUT`은 enabled 토글에만 사용.)
