# 로그인 인증 설계 (단일 계정 세션 쿠키)

작성일: 2026-06-26

## 목적

invest_portal에 단일 계정 로그인 인증을 추가한다. 추후 ytdb와의 포털 통합을 대비해 **ytdb와 동일한 인증 구조**(단일 계정 + 서명된 httpOnly 세션 쿠키, Starlette `SessionMiddleware`)를 그대로 이식한다. 동일 패턴이면 통합 시 공통 인증 레이어로 합치기 쉽다.

## 배경

- invest_portal은 단일 사용자 앱이므로 ytdb의 단일 계정 인증 패턴이 정확히 맞다.
- ytdb 참조 구현: `app/routers/auth.py`(`auth_enabled`/`require_auth`/me/login/logout), `app/main.py`(`SessionMiddleware` + 라우터별 `dependencies=[Depends(require_auth)]`), 프론트 `src/auth/{AuthProvider,useAuth}`, `src/pages/Login.tsx`, `src/api/{auth,http}.ts`.
- invest_portal엔 이미 `FERNET_KEY`가 `.env`에 있어 세션 시크릿 파생에 재사용한다.

## 인증 게이팅 정책 (ytdb와 동일)

- `AUTH_PASSWORD`가 비어 있으면 **인증 비활성**(개발 — 현재처럼 무인증 동작).
- `AUTH_PASSWORD`가 설정되면 모든 `/api` 데이터 접근에 로그인을 강제한다.
- 자격증명 비교는 상수시간(`secrets.compare_digest`).

## 백엔드 설계

### `app/config.py` — 환경설정 추가
기존 `Settings`에 4개 필드 추가:
- `AUTH_USERNAME: str = "admin"`
- `AUTH_PASSWORD: str = ""` (비어 있으면 인증 비활성)
- `SESSION_SECRET: str = ""` (비어 있으면 `FERNET_KEY`에서 파생)
- `SESSION_HTTPS_ONLY: bool = False` (https 배포 시 True)

### `app/routers/auth.py` — 신규 (ytdb 이식)
- `auth_enabled() -> bool`: `AUTH_PASSWORD` 설정 여부.
- `require_auth(request: Request) -> None`: 보호 라우터 의존성. 비활성이면 통과, 활성이면 `request.session["user"]` 없을 시 401.
- `GET /api/auth/me`: `{ auth_enabled, authenticated, username }` 반환(비활성이면 항상 authenticated=True).
- `POST /api/auth/login`: `LoginRequest{username, password}` 상수시간 비교, 성공 시 세션에 user 저장.
- `POST /api/auth/logout`: 세션 클리어, 204.

### `app/main.py` — 미들웨어 + 라우터 보호
- `SessionMiddleware` 추가: `secret_key = SESSION_SECRET or FERNET_KEY or secrets.token_urlsafe(32)`, `https_only = SESSION_HTTPS_ONLY`, `same_site="lax"`.
- 기존 라우터 일괄 등록 루프에 `dependencies=[Depends(require_auth)]` 적용.
- `auth.router`는 **무보호**로 루프 밖에서 별도 등록(로그인/상태 확인은 미인증 접근 필요).
- `/health`, SPA 서빙 라우트는 현행 유지(무인증).

## 프론트엔드 설계

### `src/api.ts` — 401 핸들러 + authApi
- `setUnauthorizedHandler(fn)` 전역 등록 + `j()` 내부에서 401 응답 시(`/auth/` 호출 제외) 핸들러 호출.
- `authApi = { me, login(username,password), logout }` (각각 `/api/auth/me|login|logout`).
- `MeResponse { auth_enabled, authenticated, username }` 타입.

### `src/auth/AuthProvider.tsx`, `src/auth/useAuth.ts` — 신규 (ytdb 이식)
- 마운트 시 `/me` 조회 → 로딩 중 스피너, 인증 활성+미인증이면 `<Login>` 렌더, 그 외 `AuthContext` 제공(`username`, `authEnabled`, `logout`).
- 세션 만료(임의 API 401) 시 `setUnauthorizedHandler`로 로그인 화면 전환.

### `src/pages/Login.tsx` — 신규 (ytdb 이식)
- 아이디/비밀번호 폼, 제출 시 `authApi.login` → 성공 시 `onLoggedIn`(refresh). 디자인 토큰 클래스(`card`/`input`/`btn-primary`)로 맞추고 제목은 "invest 로그인".

### `src/main.tsx` — AuthProvider 래핑
- `<App>`을 `<AuthProvider>`로 감싼다.

### `src/components/AppShell.tsx` — 로그아웃 배치 (방식 A)
- `useAuth()`로 `authEnabled`/`username`/`logout` 사용.
- 사이드바 하단(ThemeToggle 영역) + 모바일 탭바 헤더에 **사용자 아이디 + 로그아웃 버튼** 추가.
- 인증 비활성 시 미표시(개발 모드에서 깔끔하게).

## 검증

- 백엔드 테스트: (1) 인증 비활성 시 보호 라우터 통과, (2) 활성 시 미인증 401, (3) 로그인→세션 쿠키→통과, (4) 로그아웃→재차 401.
- 프론트: `npm run build` + `tsc` 통과.
- 수동 스모크: 사용자가 `.env`에 `AUTH_PASSWORD` 설정 후 로그인/로그아웃/세션만료 흐름 확인.

## 비목표 (YAGNI)

다중 사용자·역할, 비밀번호 변경 UI, JWT, 회원가입, "로그인 유지" 체크박스, 비밀번호 해싱(단일 계정 평문 `.env` 비교는 ytdb와 동일).

## 통합 대비 노트

- 쿠키/세션 구조를 ytdb와 동일하게 맞춰, 향후 단일 로그인 베이스 포털 통합 시 공통 인증 레이어로 교체하기 쉽게 한다.
- 통합 시 같은 도메인이면 세션 쿠키 스코프·이름 충돌을 별도 설계한다(현재는 별도 포트/도메인이라 무관).
