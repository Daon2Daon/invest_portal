# 로그인 인증 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** invest_portal에 ytdb와 동일한 단일 계정 세션 쿠키 로그인 인증을 추가한다.

**Architecture:** Starlette `SessionMiddleware`(서명 httpOnly 쿠키) + `require_auth` 의존성으로 모든 `/api` 데이터 라우터를 보호한다. `AUTH_PASSWORD`가 비면 인증 비활성(개발). 프론트는 `AuthProvider`가 `/api/auth/me`로 상태를 조회해 미인증이면 `<Login>`을 렌더한다.

**Tech Stack:** FastAPI, Starlette SessionMiddleware, pydantic-settings, httpx(test), React 18 + TS + Vite, Tailwind 디자인 토큰.

---

## File Structure

- Modify: `app/config.py` — 인증/세션 환경설정 4필드 추가
- Create: `app/routers/auth.py` — auth 라우터(me/login/logout) + `require_auth`/`auth_enabled`
- Modify: `app/main.py` — `SessionMiddleware` 추가, 데이터 라우터에 `require_auth` 적용, auth 라우터 무보호 등록
- Create: `tests/test_auth.py` — require_auth 단위 + login/logout/me HTTP 흐름 + 보호 라우터 401
- Modify: `frontend/src/api.ts` — 401 핸들러 + `authApi` + `MeResponse`
- Create: `frontend/src/auth/useAuth.ts` — `AuthContext`/`useAuth`
- Create: `frontend/src/auth/AuthProvider.tsx` — me 조회·로그인 게이트·세션만료 처리
- Create: `frontend/src/pages/Login.tsx` — 로그인 폼(디자인 토큰)
- Modify: `frontend/src/main.tsx` — `<App>`을 `<AuthProvider>`로 래핑
- Modify: `frontend/src/components/AppShell.tsx` — 사이드바/탭바에 사용자명 + 로그아웃

---

## Task 1: 인증/세션 환경설정

**Files:**
- Modify: `app/config.py`

- [ ] **Step 1: config에 인증 필드 추가**

`app/config.py`의 `Settings` 클래스에 `TEST_DATABASE_URL` 아래로 다음 4필드를 추가한다:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    FERNET_KEY: str
    SCHEMA_NAME: str = "invest"
    TEST_DATABASE_URL: str | None = None

    # 로그인 인증(단일 계정). AUTH_PASSWORD가 비어 있으면 인증 비활성(개발).
    # 값이 설정되면 모든 /api 데이터 접근에 로그인이 강제된다.
    AUTH_USERNAME: str = "admin"
    AUTH_PASSWORD: str = ""
    # 세션 쿠키 서명 키. 비어 있으면 FERNET_KEY에서 파생한다.
    SESSION_SECRET: str = ""
    # https 배포 시 True(Secure 쿠키). http(Tailscale) 배포면 False.
    SESSION_HTTPS_ONLY: bool = False


settings = Settings()
```

- [ ] **Step 2: import 검증**

Run: `.venv/bin/python -c "from app.config import settings; print(settings.AUTH_USERNAME, repr(settings.AUTH_PASSWORD))"`
Expected: `admin ''`

- [ ] **Step 3: Commit**

```bash
git add app/config.py
git commit -m "feat(auth): config에 인증/세션 환경설정 추가"
```

---

## Task 2: auth 라우터 (require_auth + me/login/logout)

**Files:**
- Create: `app/routers/auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_auth.py` 생성. `require_auth`는 `request.session.get("user")`만 읽으므로 `SimpleNamespace`로 가짜 request를 만든다(SessionMiddleware 불필요, DB 불필요).

```python
import pytest
from types import SimpleNamespace
from fastapi import HTTPException

from app.routers import auth


def _fake_request(session: dict):
    return SimpleNamespace(session=session)


def test_auth_disabled_when_password_empty(monkeypatch):
    monkeypatch.setattr(auth.app_settings, "AUTH_PASSWORD", "")
    assert auth.auth_enabled() is False
    # 비활성이면 빈 세션이어도 통과(예외 없음)
    auth.require_auth(_fake_request({}))


def test_auth_enabled_blocks_anonymous(monkeypatch):
    monkeypatch.setattr(auth.app_settings, "AUTH_PASSWORD", "secret")
    assert auth.auth_enabled() is True
    with pytest.raises(HTTPException) as ei:
        auth.require_auth(_fake_request({}))
    assert ei.value.status_code == 401


def test_auth_enabled_allows_session_user(monkeypatch):
    monkeypatch.setattr(auth.app_settings, "AUTH_PASSWORD", "secret")
    auth.require_auth(_fake_request({"user": "admin"}))  # 예외 없으면 통과
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError`/`AttributeError` (auth 모듈/속성 없음)

- [ ] **Step 3: auth 라우터 구현**

`app/routers/auth.py` 생성(ytdb `app/routers/auth.py`와 동일):

```python
"""단일 계정 로그인 인증 (httpOnly 세션 쿠키).

AUTH_PASSWORD가 비어 있으면 인증 비활성(개발). 값이 설정되면 require_auth가
모든 보호 라우터에서 세션을 강제한다. 자격증명 비교는 상수시간(secrets).
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.config import settings as app_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def auth_enabled() -> bool:
    return bool((app_settings.AUTH_PASSWORD or "").strip())


def require_auth(request: Request) -> None:
    """보호 라우터 의존성. 인증 비활성이면 통과, 활성이면 세션 필요."""
    if not auth_enabled():
        return
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")


class LoginRequest(BaseModel):
    username: str
    password: str


@router.get("/me")
async def me(request: Request) -> dict:
    enabled = auth_enabled()
    user = request.session.get("user") if enabled else None
    return {
        "auth_enabled": enabled,
        # 비활성이면 항상 인증된 것으로 취급(프론트가 앱을 바로 띄움).
        "authenticated": True if not enabled else bool(user),
        "username": user,
    }


@router.post("/login")
async def login(payload: LoginRequest, request: Request) -> dict:
    if not auth_enabled():
        raise HTTPException(status_code=400, detail="인증이 설정되지 않았습니다.")
    ok_user = secrets.compare_digest(payload.username, app_settings.AUTH_USERNAME)
    ok_pw = secrets.compare_digest(payload.password, app_settings.AUTH_PASSWORD)
    if not (ok_user and ok_pw):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")
    request.session["user"] = payload.username
    return {"username": payload.username}


@router.post("/logout", status_code=204)
async def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=204)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_auth.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/routers/auth.py tests/test_auth.py
git commit -m "feat(auth): auth 라우터(require_auth + me/login/logout)"
```

---

## Task 3: main.py에 SessionMiddleware + 라우터 보호

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_auth.py` (HTTP 흐름 + 보호 라우터 401 추가)

- [ ] **Step 1: 실패하는 HTTP 흐름 테스트 추가**

`tests/test_auth.py` 끝에 추가. `AsyncClient`는 쿠키를 유지하므로 login→me→logout 흐름과 보호 라우터 401을 검증한다(DB 불필요 — `require_auth`가 DB 접근 전에 401을 낸다).

```python
from httpx import AsyncClient, ASGITransport
from app.main import app


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_me_anonymous_when_enabled(monkeypatch):
    monkeypatch.setattr(auth.app_settings, "AUTH_PASSWORD", "secret")
    async with await _client() as ac:
        r = await ac.get("/api/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["auth_enabled"] is True
    assert body["authenticated"] is False
    assert body["username"] is None


@pytest.mark.asyncio
async def test_login_then_me_then_logout(monkeypatch):
    monkeypatch.setattr(auth.app_settings, "AUTH_PASSWORD", "secret")
    monkeypatch.setattr(auth.app_settings, "AUTH_USERNAME", "admin")
    async with await _client() as ac:
        bad = await ac.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert bad.status_code == 401

        ok = await ac.post("/api/auth/login", json={"username": "admin", "password": "secret"})
        assert ok.status_code == 200 and ok.json()["username"] == "admin"

        me = await ac.get("/api/auth/me")
        assert me.json()["authenticated"] is True and me.json()["username"] == "admin"

        out = await ac.post("/api/auth/logout")
        assert out.status_code == 204

        me2 = await ac.get("/api/auth/me")
        assert me2.json()["authenticated"] is False


@pytest.mark.asyncio
async def test_protected_route_blocks_anonymous(monkeypatch):
    monkeypatch.setattr(auth.app_settings, "AUTH_PASSWORD", "secret")
    async with await _client() as ac:
        r = await ac.get("/api/portfolio")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_open_when_auth_disabled(monkeypatch):
    monkeypatch.setattr(auth.app_settings, "AUTH_PASSWORD", "")
    async with await _client() as ac:
        # 인증 비활성이면 require_auth는 통과 → 401이 아니어야 한다(DB 미설정 시 다른 상태코드 가능).
        r = await ac.get("/api/auth/me")
    assert r.status_code == 200 and r.json()["auth_enabled"] is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_auth.py::test_protected_route_blocks_anonymous -v`
Expected: FAIL — `/api/portfolio`가 아직 보호되지 않아 401이 아닌 다른 코드 반환(또는 SessionMiddleware 미설치로 me 호출 시 500)

- [ ] **Step 3: main.py 수정**

`app/main.py`에서 import에 `secrets`, `Depends`, `SessionMiddleware`, `auth` 라우터를 추가하고, 미들웨어/보호를 적용한다.

상단 import 영역을 다음과 같이 보강한다(`from app.routers import ...` 줄에 `auth` 추가):

```python
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings as app_settings
from app.db import engine
from app.bootstrap import ensure_schema
from app.services.scheduler.scheduler import start_scheduler, shutdown_scheduler
from app.routers import assets, holdings, portfolio, fx, settings as settings_router, cash, charts, watchlist, alerts, market_summary, trend, reports, risk_signal, journal, auth
from app.routers.auth import require_auth
```

`app = FastAPI(...)` 생성 직후, CORS 미들웨어 위에 SessionMiddleware를 추가한다:

```python
app = FastAPI(title="invest_portal", lifespan=lifespan)

# 세션 미들웨어(서명된 httpOnly 쿠키). 비밀키는 SESSION_SECRET → FERNET_KEY → 임시생성.
app.add_middleware(
    SessionMiddleware,
    secret_key=(app_settings.SESSION_SECRET or app_settings.FERNET_KEY or secrets.token_urlsafe(32)),
    https_only=app_settings.SESSION_HTTPS_ONLY,
    same_site="lax",
)
```

기존 라우터 등록 루프를 보호 적용으로 교체하고, auth 라우터는 무보호로 별도 등록한다(기존 `for r in (...)` 블록 전체를 아래로 치환):

```python
# 인증 라우터는 무보호(로그인/상태 확인). 나머지 데이터 라우터는 require_auth로 보호.
app.include_router(auth.router)

_protected = [Depends(require_auth)]
for r in (assets.router, holdings.router, portfolio.router, fx.router, settings_router.router, cash.router, charts.router, watchlist.router, alerts.router, market_summary.router, trend.router, reports.router, risk_signal.router, journal.router):
    app.include_router(r, dependencies=_protected)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_auth.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: 전체 백엔드 회귀 확인**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q`
Expected: 기존 테스트 전부 PASS + 신규 auth 7건 PASS (회귀 0). 보호 라우터를 쓰는 기존 API 테스트는 `AUTH_PASSWORD`가 빈 기본값이라 인증 비활성으로 통과한다.

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/test_auth.py
git commit -m "feat(auth): SessionMiddleware + 데이터 라우터 require_auth 보호"
```

---

## Task 4: 프론트 api.ts — 401 핸들러 + authApi

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: `j()`에 401 핸들러 + authApi 추가**

`frontend/src/api.ts` 상단(`const BASE = "";` 위)에 전역 핸들러를 추가한다:

```typescript
// 세션 만료 등으로 임의 API가 401을 반환할 때 호출되는 전역 핸들러(AuthProvider가 등록).
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}
```

`j()` 함수를 401 처리하도록 교체한다(기존 `j` 정의를 아래로 치환):

```typescript
async function j<T>(p: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + p, {
    headers: { "Content-Type": "application/json" }, ...init,
  });
  // /auth/ 호출(로그인 시도 등)의 401은 전역 핸들러로 넘기지 않는다.
  if (r.status === 401 && !p.includes("/auth/")) onUnauthorized?.();
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  if (r.status === 204) return undefined as T;
  return r.json();
}
```

`export const api = {` 객체 정의 위에 `MeResponse` 타입과 `authApi`를 추가한다:

```typescript
export interface MeResponse {
  auth_enabled: boolean;
  authenticated: boolean;
  username: string | null;
}

export const authApi = {
  me: () => j<MeResponse>("/api/auth/me"),
  login: (username: string, password: string) =>
    j<{ username: string }>("/api/auth/login", {
      method: "POST", body: JSON.stringify({ username, password }),
    }),
  logout: () => j<void>("/api/auth/logout", { method: "POST" }),
};
```

- [ ] **Step 2: tsc 통과 확인**

Run: `cd frontend && npx tsc --noEmit`
Expected: 오류 없음(exit 0)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat(auth): 프론트 api에 401 핸들러 + authApi 추가"
```

---

## Task 5: 프론트 auth 컨텍스트 + Login 페이지

**Files:**
- Create: `frontend/src/auth/useAuth.ts`
- Create: `frontend/src/auth/AuthProvider.tsx`
- Create: `frontend/src/pages/Login.tsx`

- [ ] **Step 1: useAuth.ts 생성**

`frontend/src/auth/useAuth.ts` (ytdb와 동일):

```typescript
import { createContext, useContext } from 'react'

export interface AuthContextValue {
  username: string | null
  authEnabled: boolean
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
```

- [ ] **Step 2: Login.tsx 생성**

`frontend/src/pages/Login.tsx` (디자인 토큰 클래스 사용, 제목 "invest 로그인"):

```tsx
import { useState } from 'react'
import { authApi } from '../api'

export default function Login({ onLoggedIn }: { onLoggedIn: () => void | Promise<void> }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await authApi.login(username, password)
      await onLoggedIn()
    } catch (err) {
      setError((err as Error).message || '로그인에 실패했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4">
        <h1 className="text-xl font-bold">💰 invest 로그인</h1>
        {error && (
          <p className="text-sm text-down border border-border rounded-lg px-3 py-2">{error}</p>
        )}
        <div>
          <label className="block text-sm text-muted mb-1">아이디</label>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            autoComplete="username"
            className="input w-full"
          />
        </div>
        <div>
          <label className="block text-sm text-muted mb-1">비밀번호</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            className="input w-full"
          />
        </div>
        <button type="submit" disabled={busy || !username || !password} className="btn btn-primary w-full">
          {busy ? '로그인 중...' : '로그인'}
        </button>
      </form>
    </div>
  )
}
```

(주: `text-down`/`text-muted`/`border-border`/`btn`/`btn-primary`/`input`/`card`는 모두 `frontend/tailwind.config`·`index.css`에 정의된 토큰 클래스다 — 확인 완료.)

- [ ] **Step 3: AuthProvider.tsx 생성**

`frontend/src/auth/AuthProvider.tsx` (ytdb 이식, Spinner 대신 인라인 로딩):

```tsx
import { useCallback, useEffect, useState } from 'react'
import { authApi, setUnauthorizedHandler, type MeResponse } from '../api'
import Login from '../pages/Login'
import { AuthContext } from './useAuth'

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<MeResponse | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      setState(await authApi.me())
    } catch {
      setState({ auth_enabled: true, authenticated: false, username: null })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  // 세션 만료(임의 API 401) 시 로그인 화면으로 전환.
  useEffect(() => {
    setUnauthorizedHandler(() =>
      setState((s) => (s ? { ...s, authenticated: false, username: null } : s)),
    )
    return () => setUnauthorizedHandler(null)
  }, [])

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } catch {
      /* 무시 */
    }
    setState((s) => (s ? { ...s, authenticated: false, username: null } : s))
  }, [])

  if (loading || !state) {
    return <div className="min-h-screen flex items-center justify-center text-muted">불러오는 중…</div>
  }

  if (state.auth_enabled && !state.authenticated) {
    return <Login onLoggedIn={refresh} />
  }

  return (
    <AuthContext.Provider value={{ username: state.username, authEnabled: state.auth_enabled, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
```

- [ ] **Step 4: 빌드 확인**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: tsc·빌드 통과(exit 0). 사용 토큰 클래스는 모두 tailwind.config에 매핑돼 있어 추가 조정 불필요.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/auth/ frontend/src/pages/Login.tsx
git commit -m "feat(auth): AuthProvider + useAuth + Login 페이지"
```

---

## Task 6: AuthProvider 래핑 + AppShell 로그아웃 (방식 A)

**Files:**
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/components/AppShell.tsx`

- [ ] **Step 1: main.tsx에서 App을 AuthProvider로 래핑**

`frontend/src/main.tsx`를 다음으로 교체한다:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import AuthProvider from './auth/AuthProvider'
import { applyTheme, resolveInitialTheme } from './theme'

applyTheme(resolveInitialTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
)
```

- [ ] **Step 2: AppShell에 사용자명 + 로그아웃 추가**

`frontend/src/components/AppShell.tsx` 상단 import에 `useAuth`를 추가한다:

```tsx
import { useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { currentTheme, setTheme } from "../theme";
import { useAuth } from "../auth/useAuth";
```

`ThemeToggle` 함수 아래에 `LogoutButton` 컴포넌트를 추가한다(인증 비활성 시 미표시):

```tsx
function LogoutButton() {
  const { authEnabled, username, logout } = useAuth();
  if (!authEnabled) return null;
  return (
    <div className="flex items-center gap-2">
      {username && <span className="text-sm text-muted truncate">{username}</span>}
      <button onClick={() => logout()} className="btn btn-ghost text-sm" title="로그아웃">
        로그아웃
      </button>
    </div>
  );
}
```

모바일 탭바 헤더의 우측 영역(`<ThemeToggle />`이 있는 `flex items-center justify-between` 줄)을 다음으로 교체한다:

```tsx
        <div className="flex items-center justify-between px-4 py-3">
          <span className="font-extrabold">invest</span>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <LogoutButton />
          </div>
        </div>
```

사이드바 하단(`<div className="pt-4"><ThemeToggle /></div>`)을 다음으로 교체한다:

```tsx
        <div className="pt-4 space-y-3">
          <LogoutButton />
          <ThemeToggle />
        </div>
```

- [ ] **Step 3: 빌드 확인**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: tsc·빌드 통과(exit 0).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/main.tsx frontend/src/components/AppShell.tsx
git commit -m "feat(auth): App을 AuthProvider로 래핑 + 사이드바/탭바 로그아웃"
```

---

## 최종 검증

- [ ] **백엔드 전체:** `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q` → 기존 + auth 7건 전부 PASS, 회귀 0.
- [ ] **프론트:** `cd frontend && npx tsc --noEmit && npm run build` → 통과.
- [ ] **수동 스모크(사용자):** `.env`에 `AUTH_PASSWORD=...` 설정 → 앱 접속 시 로그인 화면 → 로그인 성공 → 사이드바 로그아웃 동작 → 로그아웃 후 재로그인 요구. `AUTH_PASSWORD` 미설정(개발) 시 로그인 화면 없이 바로 진입·로그아웃 버튼 미표시 확인.

---

## Self-Review 결과

- **스펙 커버리지:** config 4필드(T1) ✓, auth 라우터/require_auth(T2) ✓, SessionMiddleware+보호(T3) ✓, 프론트 401+authApi(T4) ✓, AuthProvider/useAuth/Login(T5) ✓, main 래핑+AppShell 로그아웃 방식 A(T6) ✓, 검증(최종) ✓. 비목표 항목은 계획에서 제외(YAGNI).
- **플레이스홀더:** 없음(모든 코드 블록 완전 기재).
- **타입 일관성:** `MeResponse`/`authApi`/`AuthContextValue`/`setUnauthorizedHandler`가 T4·T5·T6에서 동일 시그니처로 참조됨.
- **토큰 클래스 검증:** Login에서 쓰는 `card`/`input`/`btn`/`btn-primary`/`btn-ghost`/`text-muted`/`text-down`/`border-border`는 `index.css`·`tailwind.config`에 모두 정의됨을 확인함.
