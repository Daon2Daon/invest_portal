# 3단계 D: 투자저널 — 설계 (spec)

작성일: 2026-06-23
선행: 3단계 A(스냅샷)·B(AI 리포트)·C(위험신호) 완료. D는 3단계 마지막 하위 시스템.

## 1. 목적

사용자가 투자 생각·결정·회고를 **직접 기록**하는 자유형 저널. 날짜별 항목(제목 + 마크다운 본문)에
선택적으로 종목 1개를 연결할 수 있고(C-lite), 연결 시 자산 상세 화면에서 그 종목의 메모를 모아 보고
바로 작성할 수 있다. B(AI 리포트)가 자동 생성·이력이라면, D는 사람이 쓰는 기록이다.

## 2. 핵심 결정 요약

| 항목 | 결정 |
|------|------|
| 항목 구조 | 자유형: `entry_date + title + body(마크다운)` + 선택적 종목 1개(C-lite) |
| 종목 연결 | nullable `asset_id` FK, `ON DELETE SET NULL`(종목 삭제 시 메모 보존) |
| 자산 상세 통합 | "투자 메모" 섹션 — 해당 종목 항목 읽기 + 인라인 빠른 작성 |
| 프론트 | 신규 "저널" 메뉴/페이지 + AssetDetail 섹션 |
| 레거시 | `invest_legacy.portfolio_plans`(1건 스텁) 마이그레이션 안 함 |
| 저장 | 신규 `journal_entries` 테이블(ensure_schema 자동 생성) |

## 3. 데이터 모델 — `journal_entries`

신규 테이블 1개.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | PK | |
| `entry_date` | date, not null | 저널 날짜(미지정 시 KST 오늘) |
| `title` | text, not null | 제목 |
| `body` | text, nullable | 본문(마크다운 자유 입력, 제목만 메모도 허용) |
| `asset_id` | int FK→assets.asset_id, nullable, `ondelete=SET NULL` | 선택적 연결 종목 |
| `created_at` / `updated_at` | timestamptz | server_default now / onupdate now |

- 정렬: `entry_date` 내림차순, 동일 시 `id` 내림차순.
- `ON DELETE SET NULL`: 연결 종목이 삭제돼도 저널은 남고 연결만 해제(기존 holding/alert의 CASCADE와
  다름 — 저널은 종목과 독립적 기록이라 보존이 맞음).
- 레거시 `portfolio_plans`(context_date/summary/key_events/decisions/results/notes)는 1건 스텁뿐이라
  마이그레이션하지 않고 신규 빈 테이블로 시작.

## 4. API — `app/routers/journal.py` (`/api/journal`)

표준 CRUD(cash 라우터 패턴). Pydantic 스키마 `app/schemas/journal.py`: `JournalCreate`, `JournalUpdate`, `JournalOut`.

| 메서드 | 경로 | 동작 |
|--------|------|------|
| POST | `/api/journal` | 생성. body: `entry_date`(없으면 KST 오늘), `title`(필수), `body`(선택), `asset_id`(선택) |
| GET | `/api/journal` | 목록(최신순). 선택 쿼리 `?asset_id=X` → 해당 종목 연결 항목만 |
| GET | `/api/journal/{id}` | 단건 |
| PUT | `/api/journal/{id}` | 부분 수정(`exclude_unset`) |
| DELETE | `/api/journal/{id}` | 삭제 |

- **`JournalOut` 필드**: id, entry_date, title, body, asset_id, **asset_name·asset_ticker**(연결 종목 표시용,
  없으면 null), created_at, updated_at. 라우터가 asset_id로 자산을 조회해 이름/티커를 채운다.
- **유효성**: `asset_id`가 주어지면 존재하는 asset인지 확인(없으면 422). null/생략 허용. `title` 빈 문자열 422.
- `entry_date` 기본값: 서버에서 미지정 시 KST 오늘.
- main.py에 라우터 등록.

## 5. 프론트엔드

### 5.1 신규 메뉴 "저널"
`AppShell` 네비에 추가(리포트와 설정 사이), `/journal` → `Journal.tsx`.

### 5.2 `Journal.tsx`
- 작성 폼: 날짜(기본 오늘) · 제목 · 본문(textarea) · 종목 드롭다운(선택, "연결 안 함" 기본, `api.listAssets()` 재사용) · 저장.
- 목록: 최신순 카드 — 날짜 + 제목 + 연결 종목 배지(있으면) + 본문(`whitespace-pre-wrap`, md 렌더러 의존성 없음) + 수정/삭제(인라인 편집, reports/cash 패턴).

### 5.3 AssetDetail "투자 메모" 섹션
- `api.listJournal(assetId)`로 해당 종목 연결 항목 읽기 목록.
- 인라인 빠른 작성: 제목+본문 작은 폼 → `createJournal({asset_id, title, body})`(종목 자동 연결, 날짜 오늘) → 목록 갱신.

### 5.4 api.ts
`listJournal(assetId?)`, `getJournal(id)`, `createJournal(body)`, `updateJournal(id, body)`, `deleteJournal(id)`.

## 6. 에러 처리

- `title` 빈 값 → 422. `body`는 선택(제목만 허용).
- 존재하지 않는 `asset_id` → 422.
- 없는 항목 get/update/delete → 404.
- 종목 삭제 시 `ON DELETE SET NULL`로 저널 보존(자동, 별도 처리 없음).

## 7. 테스트 (invest_test 격리 스키마, cash/report 패턴)

- 테이블 생성: `journal_entries` 확인.
- 라우터 통합(DB): create(기본 날짜 채움·asset_name 채움) / list(최신순) / list 필터(`?asset_id`) / get / update(부분) / delete / 404 / asset_id 검증 422 / asset_id null 허용.
- ON DELETE SET NULL: 연결 자산 삭제 후 저널 잔존 + asset_id null 확인.
- 프론트 빌드·tsc 통과.

## 8. 비목표 (YAGNI)

- 레거시 `portfolio_plans` 마이그레이션, 다중 종목 태그(C-full), 첨부/이미지, 전문검색,
  AI 자동 작성(B 리포트가 담당), 태그/카테고리, 저널의 텔레그램 발송.

## 9. 단계 내 위치

3단계(AI 리포트 + 투자저널 + 위험신호) 중 **D(투자저널)** — 마지막 하위 시스템.
A(스냅샷)·B(리포트)·C(위험신호) 완료 후 진행. D 완료 시 3단계 종료 → 후속은 포털 통합.
