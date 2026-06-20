# 알림 허브 + 디자인 시스템 통합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 전체 알림을 한눈에 보고 관리하는 전용 '알림' 페이지를 추가하고, 앱 전체를 라이트/다크 토글 + 반응형(사이드바/탭바) 디자인 시스템으로 재단장한다.

**Architecture:** ① CSS 변수 토큰 + Tailwind 색상 매핑으로 라이트/다크 디자인 토대를 깔고, ② 반응형 `AppShell` 셸로 네비를 교체한 뒤, ③ 기존 페이지를 토큰 클래스로 재단장하고, ④ 알림 허브를 백엔드 목록 조회 + 새 페이지로 신규 구축한다. 백엔드 신규 코드는 "전체 알림 조회" 하나뿐(생성/수정/삭제/재무장은 기존 엔드포인트 재사용).

**Tech Stack:** FastAPI + async SQLAlchemy(백엔드), React 18 + Vite + TS + Tailwind(프론트), pytest(invest_test 격리 스키마).

**검증 명령:**
- 백엔드 테스트: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q`
- 프론트 빌드: `cd frontend && npm run build`
- dev 구동: 백엔드 `.venv/bin/uvicorn app.main:app`, 프론트 `cd frontend && npm run dev`(localhost:5173)

---

## 파일 구조

**백엔드**
- Modify: `app/services/alert/alert_store.py` — `list_all_alerts_view(db)` 추가 + `list_alerts_view`의 항목 계산을 `_alert_row(...)` 헬퍼로 추출(공유).
- Modify: `app/routers/alerts.py` — `GET /api/alerts`의 `asset_id`를 선택값으로.
- Test: `tests/test_alert_store.py`, `tests/test_alerts_api.py` 에 케이스 추가.

**프론트 (foundation)**
- Modify: `frontend/tailwind.config.js` — 토큰 색상 매핑.
- Modify: `frontend/src/index.css` — Vite 잔재 제거 + 라이트/다크 토큰 + 공용 컴포넌트 클래스.
- Create: `frontend/src/theme.ts` — 테마 초기화/토글 유틸.
- Create: `frontend/src/components/AppShell.tsx` — 반응형 네비 셸.
- Modify: `frontend/src/App.tsx` — `AppShell`로 래핑 + '알림' 라우트.
- Modify: `frontend/src/main.tsx` — 부팅 시 테마 적용.

**프론트 (alerts hub)**
- Modify: `frontend/src/api.ts` — `listAllAlerts`, `updateAlert` 추가 + `AlertRow` 타입.
- Create: `frontend/src/components/AlertForm.tsx` — AssetDetail/Alerts 공용 알림 추가 폼.
- Create: `frontend/src/pages/Alerts.tsx` — 알림 허브.
- Modify: `frontend/src/pages/AssetDetail.tsx` — 알림 폼을 `AlertForm`으로 교체.
- Modify: `frontend/src/pages/Dashboard.tsx`, `frontend/src/pages/Watchlist.tsx` — 알림 개수 배지.

**프론트 (restyle)**
- Modify: `Dashboard.tsx`, `Holdings.tsx`, `Watchlist.tsx`, `AssetDetail.tsx`, `Settings.tsx` — 토큰 클래스로 재단장.

---

# Phase 1 — 디자인 토대

### Task 1: Tailwind 토큰 색상 매핑

**Files:**
- Modify: `frontend/tailwind.config.js`

- [ ] **Step 1: tailwind.config.js 전체 교체**

```js
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        border: "var(--border)",
        text: "var(--text)",
        muted: "var(--text-muted)",
        accent: "var(--accent)",
        "accent-fg": "var(--accent-fg)",
        up: "var(--up)",
        down: "var(--down)",
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/tailwind.config.js
git commit -m "feat(ui): 토큰 색상 Tailwind 매핑"
```

---

### Task 2: index.css 토큰 + 공용 클래스 (Vite 잔재 제거)

**Files:**
- Modify: `frontend/src/index.css` (전체 교체)

- [ ] **Step 1: index.css 전체를 아래로 교체**

기존 `#root{width:1126px}`·`h1 56px`·`code`·`#social` 등 Vite 잔재를 전부 제거하고 토큰 + 공용 컴포넌트 클래스만 둔다.

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root,
:root[data-theme="light"] {
  --bg: #f7f8fa;
  --surface: #ffffff;
  --surface-2: #f2f4f6;
  --border: #e7e7ea;
  --text: #1a1a20;
  --text-muted: #6b7280;
  --accent: #7c5cff;
  --accent-fg: #ffffff;
  --up: #e5484d;   /* 상승 = 빨강 (KR 관례) */
  --down: #3b82f6; /* 하락 = 파랑 */
}

:root[data-theme="dark"] {
  --bg: #0f1115;
  --surface: #161922;
  --surface-2: #1f2430;
  --border: #262b36;
  --text: #f1f3f6;
  --text-muted: #8b91a0;
  --accent: #a78bfa;
  --accent-fg: #15151a;
  --up: #ef5350;
  --down: #5b9dff;
}

html, body, #root {
  margin: 0;
  min-height: 100vh;
}

body {
  background: var(--bg);
  color: var(--text);
  font: 15px/1.5 system-ui, "Segoe UI", Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
}

@layer components {
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 0.75rem;
    padding: 1rem;
  }
  .btn {
    border-radius: 0.5rem;
    padding: 0.4rem 0.8rem;
    font-size: 0.875rem;
    font-weight: 500;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
  }
  .btn:disabled { opacity: 0.5; cursor: default; }
  .btn-primary {
    background: var(--accent);
    color: var(--accent-fg);
    border-color: var(--accent);
  }
  .btn-ghost { background: transparent; }
  .input {
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    border-radius: 0.5rem;
    padding: 0.35rem 0.6rem;
    font-size: 0.875rem;
  }
  .badge {
    display: inline-flex;
    align-items: center;
    padding: 0.1rem 0.5rem;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 600;
    background: var(--accent);
    color: var(--accent-fg);
  }
}
```

- [ ] **Step 2: 빌드 통과 확인**

Run: `cd frontend && npm run build`
Expected: 빌드 성공(타입/CSS 에러 없음). 화면 스타일이 깨져 보여도 무방(다음 태스크에서 셸·페이지 적용).

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/index.css
git commit -m "feat(ui): 라이트/다크 토큰 + 공용 컴포넌트 클래스, Vite 잔재 제거"
```

---

### Task 3: 테마 초기화/토글 유틸

**Files:**
- Create: `frontend/src/theme.ts`

- [ ] **Step 1: theme.ts 작성**

```ts
// 라이트/다크 테마: 저장값 우선, 없으면 시스템 설정. <html data-theme>에 적용.
export type Theme = "light" | "dark";

const KEY = "theme";

export function resolveInitialTheme(): Theme {
  const saved = localStorage.getItem(KEY);
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(t: Theme) {
  document.documentElement.setAttribute("data-theme", t);
}

export function setTheme(t: Theme) {
  localStorage.setItem(KEY, t);
  applyTheme(t);
}

export function currentTheme(): Theme {
  return (document.documentElement.getAttribute("data-theme") as Theme) || "light";
}
```

- [ ] **Step 2: main.tsx에서 부팅 시 적용**

`frontend/src/main.tsx`를 아래로 교체:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { applyTheme, resolveInitialTheme } from './theme'

applyTheme(resolveInitialTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

- [ ] **Step 3: 빌드 통과 확인**

Run: `cd frontend && npm run build`
Expected: 빌드 성공.

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/theme.ts frontend/src/main.tsx
git commit -m "feat(ui): 테마 초기화/토글 유틸 + 부팅 적용"
```

---

### Task 4: 반응형 AppShell 셸

**Files:**
- Create: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: AppShell.tsx 작성**

`lg`(~1024px) 이상=좌측 사이드바, 미만=상단 탭바. 테마 토글 버튼 포함.

```tsx
import { ReactNode, useState } from "react";
import { NavLink } from "react-router-dom";
import { currentTheme, setTheme, type Theme } from "../theme";

const NAV = [
  { to: "/", label: "포트폴리오", end: true },
  { to: "/watchlist", label: "관심종목" },
  { to: "/alerts", label: "알림" },
  { to: "/manage", label: "관리" },
  { to: "/settings", label: "설정" },
];

function ThemeToggle() {
  const [t, setT] = useState<Theme>(currentTheme());
  const flip = () => { const n = t === "dark" ? "light" : "dark"; setTheme(n); setT(n); };
  return (
    <button onClick={flip} className="btn btn-ghost text-sm" title="테마 전환">
      {t === "dark" ? "☀️ 라이트" : "🌙 다크"}
    </button>
  );
}

function links(onClick?: () => void) {
  return NAV.map((n) => (
    <NavLink
      key={n.to}
      to={n.to}
      end={n.end}
      onClick={onClick}
      className={({ isActive }) =>
        `block rounded-lg px-3 py-2 text-sm ${isActive ? "bg-surface-2 text-accent font-semibold" : "text-muted hover:text-text"}`
      }
    >
      {n.label}
    </NavLink>
  ));
}

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen lg:flex">
      {/* 좁은 화면: 상단 탭바 */}
      <header className="lg:hidden border-b border-border bg-surface">
        <div className="flex items-center justify-between px-4 py-3">
          <span className="font-extrabold">invest</span>
          <ThemeToggle />
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2">{links()}</nav>
      </header>

      {/* 넓은 화면: 좌측 사이드바 */}
      <aside className="hidden lg:flex lg:w-56 lg:flex-col lg:border-r lg:border-border lg:bg-surface lg:p-4">
        <div className="mb-6 flex items-center justify-between">
          <span className="font-extrabold">💰 invest</span>
        </div>
        <nav className="flex-1 space-y-1">{links()}</nav>
        <div className="pt-4"><ThemeToggle /></div>
      </aside>

      <main className="flex-1">{children}</main>
    </div>
  );
}
```

- [ ] **Step 2: App.tsx 교체 (AppShell 래핑 + /alerts 라우트)**

```tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import AppShell from "./components/AppShell";
import Dashboard from "./pages/Dashboard";
import Holdings from "./pages/Holdings";
import Watchlist from "./pages/Watchlist";
import Alerts from "./pages/Alerts";
import AssetDetail from "./pages/AssetDetail";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/manage" element={<Holdings />} />
          <Route path="/asset/:id" element={<AssetDetail />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}
```

> 주의: `Alerts` 페이지는 Task 10에서 생성한다. 그 전까지 빌드가 깨지므로, **이 태스크 Step 2는 Task 10 완료 후에 `/alerts` 라우트를 추가**하거나, 임시로 `const Alerts = () => <div className="p-6">준비 중</div>;` 스텁을 두고 진행한다. 여기서는 스텁 방식으로 진행:

App.tsx 상단의 `import Alerts ...` 줄 대신 임시 스텁을 둔다(Task 10에서 실제 import로 교체):

```tsx
// 임시 스텁 — Task 10에서 실제 페이지로 교체
const Alerts = () => <div className="p-6">알림 페이지 준비 중…</div>;
```

- [ ] **Step 3: 빌드 + dev 수동 확인**

Run: `cd frontend && npm run build`
Expected: 빌드 성공.
수동: dev에서 창 너비를 1024px 위/아래로 바꿔 사이드바↔탭바 전환, 테마 토글 버튼으로 라이트↔다크 전환 후 새로고침해도 유지되는지 확인.

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/components/AppShell.tsx frontend/src/App.tsx
git commit -m "feat(ui): 반응형 AppShell(사이드바/탭바) + 테마 토글 + 알림 라우트 스텁"
```

---

# Phase 2 — 기존 페이지 재단장

> **공통 매핑 규칙(모든 페이지 동일 적용):**
> - `bg-white` → `bg-surface`
> - `border`(색 미지정) → `border border-border`
> - `text-gray-500/400` → `text-muted`
> - `bg-gray-50/100` → `bg-surface-2`
> - `bg-blue-600 text-white`(주요 버튼) → `btn btn-primary`
> - `bg-gray-500/800 text-white`(보조 버튼) → `btn`
> - `text-red-600`(상승/이익) → `text-up`
> - `text-blue-600`(하락/손실) → `text-down`
> - 카드 컨테이너 `rounded border p-4` → `card`
> - `<input ... className="border rounded px-2 py-1">` → `className="input"`
> - 페이지 루트 `div`는 `p-6 space-y-4` 유지(콘텐츠 패딩). 표는 `text-text`가 기본이므로 색 지정 불필요.

### Task 5: Dashboard 재단장

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: 위 매핑 규칙대로 클래스 치환**

구체:
- 요약 카드 3개: `rounded border p-4` → `card`. 라벨 `text-gray-500` → `text-muted`.
- "새로고침" 버튼: `px-3 py-1.5 rounded bg-blue-600 text-white disabled:opacity-50` → `btn btn-primary`.
- 표 헤더 `border-b text-left text-gray-500` → `border-b border-border text-left text-muted`.
- 행 `border-b hover:bg-gray-50` → `border-b border-border hover:bg-surface-2`.
- 손익 `text-red-600`/`text-blue-600` → `text-up`/`text-down` (2곳: 요약 + 행).
- ticker 보조텍스트 `text-gray-400` → `text-muted`.
- 현금/자산군 표도 동일 매핑.

- [ ] **Step 2: 빌드 확인**

Run: `cd frontend && npm run build`
Expected: 성공.

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "style(ui): Dashboard 토큰 재단장"
```

---

### Task 6: Watchlist 재단장

**Files:**
- Modify: `frontend/src/pages/Watchlist.tsx`

- [ ] **Step 1: 매핑 규칙 적용**(Dashboard와 동일 패턴: 카드/표/버튼/손익색). 페이지를 열어 `bg-white`/`border`/`text-gray-*`/`bg-blue-600`/`text-red-600`/`text-blue-600`을 규칙대로 치환.

- [ ] **Step 2: 빌드 확인** — Run: `cd frontend && npm run build` → 성공.

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/pages/Watchlist.tsx
git commit -m "style(ui): Watchlist 토큰 재단장"
```

---

### Task 7: Holdings 재단장

**Files:**
- Modify: `frontend/src/pages/Holdings.tsx`

- [ ] **Step 1: 매핑 규칙 적용.** 입력 폼이 많은 페이지이므로 `<input>`/`<select>`의 `border rounded px-2 py-1` 류를 `input` 클래스로, 주요 버튼을 `btn btn-primary`, 삭제/보조 버튼을 `btn`으로 치환. 인라인 수정 영역의 카드도 `card`.

- [ ] **Step 2: 빌드 확인** — Run: `cd frontend && npm run build` → 성공.

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/pages/Holdings.tsx
git commit -m "style(ui): Holdings 토큰 재단장"
```

---

### Task 8: Settings 재단장

**Files:**
- Modify: `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: 매핑 규칙 적용.** 섹션 컨테이너 → `card`, 입력 → `input`, 저장 버튼 → `btn btn-primary`, 보조 버튼 → `btn`, 보조 텍스트 → `text-muted`.

- [ ] **Step 2: 빌드 확인** — Run: `cd frontend && npm run build` → 성공.

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/pages/Settings.tsx
git commit -m "style(ui): Settings 토큰 재단장"
```

---

# Phase 3 — 알림 허브

### Task 9: 백엔드 — 전체 알림 조회

**Files:**
- Modify: `app/services/alert/alert_store.py`
- Modify: `app/routers/alerts.py`
- Test: `tests/test_alert_store.py`, `tests/test_alerts_api.py`

- [ ] **Step 1: 실패하는 store 테스트 작성**

`tests/test_alert_store.py` 끝에 추가:

```python
@pytest.mark.asyncio
async def test_list_all_alerts_view_groups_and_enriches(db_session, monkeypatch):
    from app.services.market.quote_service import quote_service  # noqa: F401 (참조 경로 확인용)
    a1 = _asset(ticker="ALLA", name="에이", fetch_symbol="ALLA")
    a2 = _asset(ticker="ALLB", name="비", fetch_symbol="ALLB")
    inactive = _asset(ticker="ALLC", fetch_symbol="ALLC", is_active=False)
    db_session.add_all([a1, a2, inactive]); await db_session.commit()
    await alert_store.create_alert(db_session, a1.asset_id, "ABSOLUTE", "ABOVE", 100.0)
    await alert_store.create_alert(db_session, a1.asset_id, "ABSOLUTE", "BELOW", 50.0)
    await alert_store.create_alert(db_session, a2.asset_id, "ABSOLUTE", "ABOVE", 10.0)
    await alert_store.create_alert(db_session, inactive.asset_id, "ABSOLUTE", "ABOVE", 1.0)
    await db_session.commit()

    calls = {"n": 0}
    from types import SimpleNamespace
    async def fake_quote(asset):
        calls["n"] += 1
        return SimpleNamespace(price=75.0, status="ok")
    monkeypatch.setattr("app.services.alert.alert_store.get_quote", fake_quote)

    rows = await alert_store.list_all_alerts_view(db_session)
    # 비활성 자산 제외 → 3건
    assert len(rows) == 3
    # 자산당 quote 1회(2개 활성 자산) — 알림 3건이어도 호출 2회
    assert calls["n"] == 2
    # 자산 메타 포함
    assert {r["asset_name"] for r in rows} == {"에이", "비"}
    assert all("ticker" in r and "target_price" in r for r in rows)
```

- [ ] **Step 2: 실패 확인**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_alert_store.py::test_list_all_alerts_view_groups_and_enriches -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'list_all_alerts_view'`.

- [ ] **Step 3: store 구현**

`app/services/alert/alert_store.py`에서 기존 `list_alerts_view`의 항목 계산을 헬퍼로 추출하고, 전체 조회를 추가한다. 파일 하단(import 줄들 아래)을 아래로 교체:

```python
from app.services.market.quote_service import get_quote
from app.services.alert.basis import resolve_basis_price
from app.services.alert.evaluator import compute_target, is_fired


async def _alert_row(db: AsyncSession, asset: Asset, a: PriceAlert, cur: float | None,
                     price_status: str) -> dict:
    """단일 알림 + 라이브(목표가·발동여부) 계산. cur는 자산 현재가(없으면 None)."""
    bp = await resolve_basis_price(db, asset, a.basis)
    target = (compute_target(a.basis, a.direction, float(a.value), bp)
              if (bp is not None or a.basis == "ABSOLUTE") else None)
    fired = bool(cur is not None and target is not None
                 and is_fired(a.direction, cur, target))
    return {
        "alert_id": a.alert_id, "asset_id": a.asset_id, "basis": a.basis,
        "direction": a.direction, "value": float(a.value), "enabled": a.enabled,
        "is_triggered": a.is_triggered, "note": a.note,
        "target_price": target, "current_price": cur,
        "price_status": price_status, "fired": fired,
    }


async def list_alerts_view(db: AsyncSession, asset_id: int) -> list[dict]:
    """자산의 알림 + 라이브 계산. 자산 없으면 빈 리스트."""
    asset = await db.get(Asset, asset_id)
    if asset is None:
        return []
    alerts = await list_by_asset(db, asset_id)
    quote = await get_quote(asset)
    cur = quote.price if quote.status == "ok" else None
    return [await _alert_row(db, asset, a, cur, quote.status) for a in alerts]


async def list_all_alerts_view(db: AsyncSession) -> list[dict]:
    """모든 활성 자산의 알림(enabled/triggered 무관) + 자산 메타 + 라이브 계산.
    자산당 시세 1회만 조회. 발동/예정 항목을 위로, 그다음 종목명 정렬."""
    rows = (await db.execute(
        select(PriceAlert, Asset).join(Asset, Asset.asset_id == PriceAlert.asset_id)
        .where(Asset.is_active.is_(True)).order_by(PriceAlert.asset_id, PriceAlert.alert_id)
    )).all()
    # asset_id별 그룹
    by_asset: dict[int, tuple[Asset, list[PriceAlert]]] = {}
    for alert, asset in rows:
        by_asset.setdefault(asset.asset_id, (asset, []))[1].append(alert)

    out: list[dict] = []
    for asset, alerts in by_asset.values():
        quote = await get_quote(asset)
        cur = quote.price if quote.status == "ok" else None
        for a in alerts:
            row = await _alert_row(db, asset, a, cur, quote.status)
            row.update(asset_name=asset.name, ticker=asset.ticker,
                       market=asset.market, asset_class=asset.asset_class)
            out.append(row)
    out.sort(key=lambda r: (not (r["fired"] or r["is_triggered"]), r["asset_name"]))
    return out
```

(기존 파일 하단의 `list_alerts_view` 정의와 그 위의 import 3줄을 위 블록으로 대체. `select, func`는 파일 상단에 이미 import됨.)

- [ ] **Step 4: store 테스트 통과 확인**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_alert_store.py -q`
Expected: PASS (신규 + 기존 store 테스트 모두).

- [ ] **Step 5: 실패하는 라우터 테스트 작성**

`tests/test_alerts_api.py` 끝에 추가:

```python
@pytest.mark.asyncio
async def test_list_all_uses_all_view():
    rows = [{"alert_id": 1, "asset_id": 1, "basis": "ABSOLUTE", "direction": "ABOVE",
             "value": 250.0, "enabled": True, "is_triggered": False, "note": None,
             "target_price": 250.0, "current_price": 251.0, "price_status": "ok",
             "fired": True, "asset_name": "에이", "ticker": "AAA", "market": "US",
             "asset_class": "주식"}]
    with patch("app.routers.alerts.list_all_alerts_view", AsyncMock(return_value=rows)):
        async with await _client() as ac:
            resp = await ac.get("/api/alerts")
    assert resp.status_code == 200
    assert resp.json()[0]["asset_name"] == "에이"
```

(상단 import에 `from app.services.alert.alert_store import list_alerts_view`가 이미 있으니, 라우터에서 `list_all_alerts_view`도 import해 patch 경로 `app.routers.alerts.list_all_alerts_view`가 유효해야 한다 — 다음 스텝에서 처리.)

- [ ] **Step 6: 실패 확인**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_alerts_api.py::test_list_all_uses_all_view -q`
Expected: FAIL (asset_id 누락으로 422, 또는 import 에러).

- [ ] **Step 7: 라우터 구현**

`app/routers/alerts.py`의 import와 `list_alerts` 핸들러를 수정:

import 줄 교체:
```python
from app.services.alert.alert_store import list_alerts_view, list_all_alerts_view
```

`list_alerts` 핸들러 교체:
```python
@router.get("")
async def list_alerts(asset_id: int | None = None, db: AsyncSession = Depends(get_db)):
    if asset_id is None:
        return await list_all_alerts_view(db)
    return await list_alerts_view(db, asset_id)
```

- [ ] **Step 8: 전체 백엔드 테스트 통과 확인**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q`
Expected: 전부 PASS(기존 155 + 신규 2).

- [ ] **Step 9: 커밋**

```bash
git add app/services/alert/alert_store.py app/routers/alerts.py tests/test_alert_store.py tests/test_alerts_api.py
git commit -m "feat(alerts): 전체 알림 조회(list_all_alerts_view) + GET /api/alerts asset_id 선택화"
```

---

### Task 10: 프론트 — api/타입 + AlertForm 공용 컴포넌트 + Alerts 페이지

**Files:**
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/components/AlertForm.tsx`
- Create: `frontend/src/pages/Alerts.tsx`
- Modify: `frontend/src/App.tsx` (스텁 → 실제 import)

- [ ] **Step 1: api.ts에 메서드/타입 추가**

`api` 객체에 추가(기존 `listAlerts` 아래):
```ts
  listAllAlerts: () => j<AlertRow[]>("/api/alerts"),
  updateAlert: (id: number, a: { value?: number; direction?: AlertDirection; enabled?: boolean }) =>
    j(`/api/alerts/${id}`, { method: "PUT", body: JSON.stringify(a) }),
```

파일 끝 타입 영역에 추가:
```ts
export interface AlertRow extends AlertView {
  asset_name: string; ticker: string; market: string; asset_class: string | null;
}
```

- [ ] **Step 2: AlertForm.tsx 작성 (AssetDetail/Alerts 공용)**

기준 옵션 비활성 로직을 한 곳에 둔다. `assetPicker`가 true면 종목 드롭다운을 보여주고, false면 고정 asset(상세 페이지)으로 동작.

```tsx
import { useState } from "react";
import { api } from "../api";
import type { AlertBasis, AlertDirection } from "../api";

export const BASIS_LABEL: Record<AlertBasis, string> = {
  ABSOLUTE: "절대 목표가", PURCHASE_AVG: "평균매입가 대비",
  WEEK52_HIGH: "52주 고점 대비", WEEK52_LOW: "52주 저점 대비",
};

export interface AssetOpt { asset_id: number; label: string; held: boolean; manual: boolean; }

export function basisDisabled(b: AlertBasis, held: boolean, manual: boolean) {
  return (b === "PURCHASE_AVG" && !held) ||
    ((b === "WEEK52_HIGH" || b === "WEEK52_LOW") && manual);
}

interface Props {
  /** 종목 선택형(알림 허브)이면 목록 전달, 상세 페이지면 fixed 전달 */
  options?: AssetOpt[];
  fixed?: { asset_id: number; held: boolean; manual: boolean };
  onAdded: () => void;
}

export default function AlertForm({ options, fixed, onAdded }: Props) {
  const [sel, setSel] = useState<number | "">(fixed ? fixed.asset_id : "");
  const [basis, setBasis] = useState<AlertBasis>("ABSOLUTE");
  const [dir, setDir] = useState<AlertDirection>("ABOVE");
  const [value, setValue] = useState("");
  const [msg, setMsg] = useState("");

  const selectedOpt = fixed ? undefined : options?.find((o) => o.asset_id === sel);
  const cur: { asset_id: number; held: boolean; manual: boolean } | undefined =
    fixed
      ? fixed
      : selectedOpt
        ? { asset_id: selectedOpt.asset_id, held: selectedOpt.held, manual: selectedOpt.manual }
        : undefined;

  const unit = basis === "ABSOLUTE" ? "가격" : "%";
  const add = async () => {
    if (!cur) { setMsg("종목을 선택하세요"); return; }
    setMsg("");
    try {
      await api.createAlert({ asset_id: cur.asset_id, basis, direction: dir, value: Number(value) });
      setValue(""); onAdded();
    } catch (e: any) { setMsg("추가 실패: " + e.message); }
  };

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {options && (
        <select className="input" value={sel}
          onChange={(e) => setSel(e.target.value === "" ? "" : Number(e.target.value))}>
          <option value="">종목 선택…</option>
          {options.map((o) => <option key={o.asset_id} value={o.asset_id}>{o.label}</option>)}
        </select>
      )}
      <select className="input" value={basis} onChange={(e) => setBasis(e.target.value as AlertBasis)}>
        {(Object.keys(BASIS_LABEL) as AlertBasis[]).map((b) => (
          <option key={b} value={b}
            disabled={!!cur && basisDisabled(b, cur.held, cur.manual)}>{BASIS_LABEL[b]}</option>
        ))}
      </select>
      <select className="input" value={dir} onChange={(e) => setDir(e.target.value as AlertDirection)}>
        <option value="ABOVE">이상 도달</option>
        <option value="BELOW">이하 도달</option>
      </select>
      <input className="input w-28" placeholder={unit} value={value}
        onChange={(e) => setValue(e.target.value)} />
      <span className="text-xs text-muted">{unit}</span>
      <button onClick={add} className="btn btn-primary">추가</button>
      {msg && <span className="text-sm text-muted">{msg}</span>}
    </div>
  );
}
```

- [ ] **Step 3: Alerts.tsx 작성**

```tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { AlertRow } from "../api";
import AlertForm, { BASIS_LABEL, type AssetOpt } from "../components/AlertForm";

export default function Alerts() {
  const nav = useNavigate();
  const [rows, setRows] = useState<AlertRow[]>([]);
  const [opts, setOpts] = useState<AssetOpt[]>([]);
  const [loading, setLoading] = useState(true);

  const loadRows = async () => setRows(await api.listAllAlerts());
  const loadOpts = async () => {
    const [pf, wl] = await Promise.all([api.portfolio(), api.listWatchlist()]);
    const held: AssetOpt[] = pf.positions.map((p) => ({
      asset_id: p.asset_id, label: `${p.name} (${p.ticker})`, held: true, manual: false,
    }));
    const heldIds = new Set(held.map((h) => h.asset_id));
    const watch: AssetOpt[] = wl
      .filter((w) => !heldIds.has(w.asset_id))
      .map((w) => ({ asset_id: w.asset_id, label: `${w.name} (${w.ticker})`, held: false, manual: false }));
    setOpts([...held, ...watch]);
  };
  useEffect(() => {
    (async () => { try { await Promise.all([loadRows(), loadOpts()]); } finally { setLoading(false); } })();
  }, []);

  const toggle = async (r: AlertRow) => { await api.updateAlert(r.alert_id, { enabled: !r.enabled }); await loadRows(); };
  const rearm = async (id: number) => { await api.rearmAlert(id); await loadRows(); };
  const del = async (id: number) => { await api.deleteAlert(id); await loadRows(); };

  if (loading) return <div className="p-6">불러오는 중…</div>;
  return (
    <div className="p-6 space-y-4">
      <h1 className="text-xl font-bold">알림</h1>
      <div className="card space-y-2">
        <h2 className="font-semibold">알림 추가</h2>
        <AlertForm options={opts} onAdded={loadRows} />
      </div>
      {rows.length === 0 ? (
        <p className="text-muted text-sm">설정된 알림이 없습니다. 위에서 추가하거나 종목 상세에서 설정하세요.</p>
      ) : (
        <table className="w-full text-sm border-collapse">
          <thead><tr className="border-b border-border text-left text-muted">
            <th className="py-2">종목</th><th>기준</th><th>방향</th><th>목표가</th><th>현재가</th><th>상태</th><th></th>
          </tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.alert_id} className="border-b border-border hover:bg-surface-2">
                <td className="py-2 cursor-pointer" onClick={() => nav(`/asset/${r.asset_id}`)}>
                  {r.asset_name} <span className="text-muted">{r.ticker}·{r.market}</span>
                </td>
                <td>{BASIS_LABEL[r.basis]}</td>
                <td>{r.direction === "ABOVE" ? "이상" : "이하"} {r.value}{r.basis === "ABSOLUTE" ? "" : "%"}</td>
                <td>{r.target_price == null ? "—" : r.target_price.toLocaleString()}</td>
                <td>{r.current_price == null ? "—" : r.current_price.toLocaleString()}</td>
                <td>
                  {r.is_triggered ? <span className="text-muted">발동됨</span>
                    : r.enabled ? <span className="text-up">활성</span>
                    : <span className="text-muted">꺼짐</span>}
                </td>
                <td className="whitespace-nowrap">
                  {r.is_triggered
                    ? <button onClick={() => rearm(r.alert_id)} className="text-accent mr-2">재무장</button>
                    : <button onClick={() => toggle(r)} className="text-accent mr-2">{r.enabled ? "끄기" : "켜기"}</button>}
                  <button onClick={() => del(r.alert_id)} className="text-up">삭제</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

- [ ] **Step 4: App.tsx 스텁 → 실제 import**

App.tsx에서 임시 스텁 `const Alerts = ...` 줄을 제거하고 상단에 실제 import 추가:
```tsx
import Alerts from "./pages/Alerts";
```

- [ ] **Step 5: 빌드 확인**

Run: `cd frontend && npm run build`
Expected: 성공.

- [ ] **Step 6: 커밋**

```bash
git add frontend/src/api.ts frontend/src/components/AlertForm.tsx frontend/src/pages/Alerts.tsx frontend/src/App.tsx
git commit -m "feat(alerts): 알림 허브 페이지 + 공용 AlertForm + api"
```

---

### Task 11: AssetDetail에서 AlertForm 재사용 + 재단장

**Files:**
- Modify: `frontend/src/pages/AssetDetail.tsx`

- [ ] **Step 1: 알림 폼 영역을 AlertForm으로 교체**

AssetDetail의 알림 "추가" 폼(현재 `aBasis/aDir/aValue/addAlert` 인라인 select들, 약 171~188줄)을 `AlertForm`으로 교체한다. 관련 상태(`aBasis, aDir, aValue, aMsg, BASIS_LABEL, basisDisabled, valueUnit, addAlert`)와 import 중 폼 전용 부분을 제거하고 아래로 대체:

import에 추가:
```tsx
import AlertForm, { BASIS_LABEL } from "../components/AlertForm";
```
(기존 파일 내 로컬 `BASIS_LABEL` 정의는 제거하고 import 사용. 목록 렌더의 `BASIS_LABEL[al.basis]`는 그대로 동작.)

알림 카드의 추가 폼 부분을 교체:
```tsx
      <div className="card max-w-3xl space-y-3">
        <h2 className="font-semibold">가격 알림</h2>
        <AlertForm
          fixed={{ asset_id: assetId, held: !!detail?.held, manual: detail?.asset.data_source === "manual" }}
          onAdded={reloadAlerts}
        />
        {/* 기존 알림 목록 테이블은 유지(아래) */}
```
> 주의: `fixed`는 `assetId`(non-null 보장된 위치)와 `detail`을 사용한다. `detail`이 아직 null이면 held/manual은 기본 false로 시작하고, detail 로드 후 재렌더된다. 폼은 detail 로드 후에만 의미 있으므로, 알림 카드 전체를 `{detail && ( ... )}`로 감싸도 좋다.

남은 `aMsg` 등 폼 전용 상태와 `addAlert`, `valueUnit`, `basisDisabled`, `isManual`, `held` 중 폼에서만 쓰던 것은 제거(목록/다른 곳에서 쓰면 유지).

- [ ] **Step 2: 페이지 재단장(매핑 규칙)**

Phase 2 공통 매핑을 AssetDetail에도 적용: `border rounded p-3 bg-white` → `card`, 버튼들(`bg-gray-800/emerald-600/blue-600/gray-500 text-white`) → `btn`/`btn btn-primary`, 손익 `text-red-600`/`text-blue-600` → `text-up`/`text-down`, 보조텍스트 → `text-muted`, 분석 패널 `bg-gray-50` → `bg-surface-2`, 요일/입력 버튼의 `bg-blue-600`/`bg-gray-100` → `btn btn-primary`/`btn`. 보유/관심 뱃지의 `bg-blue-100 text-blue-700`/`bg-gray-100` → `badge`/`bg-surface-2 text-muted px-2 py-0.5 rounded`.

- [ ] **Step 3: 빌드 확인** — Run: `cd frontend && npm run build` → 성공.

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/pages/AssetDetail.tsx
git commit -m "refactor(alerts): AssetDetail 알림 폼을 공용 AlertForm으로 + 재단장"
```

---

### Task 12: 알림 개수 배지 (Dashboard / Watchlist)

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/pages/Watchlist.tsx`

- [ ] **Step 1: Dashboard에 배지 추가**

`api.listAllAlerts()`를 한 번 불러 `asset_id`별 활성(enabled && !is_triggered) 카운트를 만든다.

상태/로드 추가:
```tsx
import type { AlertRow } from "../api";
// ...
const [alertCount, setAlertCount] = useState<Record<number, number>>({});
// load() 안 또는 useEffect에:
api.listAllAlerts().then((rows: AlertRow[]) => {
  const m: Record<number, number> = {};
  rows.forEach((r) => { if (r.enabled && !r.is_triggered) m[r.asset_id] = (m[r.asset_id] || 0) + 1; });
  setAlertCount(m);
}).catch(() => {});
```

종목 행의 종목명 셀에 배지 추가(클릭 시 알림 페이지로; 행 클릭 전파 방지):
```tsx
{alertCount[p.asset_id] ? (
  <span className="badge ml-2 cursor-pointer"
    onClick={(e) => { e.stopPropagation(); nav("/alerts"); }}>🔔 {alertCount[p.asset_id]}</span>
) : null}
```

- [ ] **Step 2: Watchlist에 동일 배지 추가**

Watchlist에도 같은 방식으로 `alertCount`를 만들고, 각 종목 행에 동일 배지를 추가한다(행 진입이 종목 상세면 `e.stopPropagation()` 후 `nav("/alerts")`).

- [ ] **Step 3: 빌드 확인** — Run: `cd frontend && npm run build` → 성공.

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/pages/Dashboard.tsx frontend/src/pages/Watchlist.tsx
git commit -m "feat(alerts): 포트폴리오/관심종목 행에 알림 개수 배지"
```

---

### Task 13: 최종 검증 (실DB 스모크 + 수동 확인)

- [ ] **Step 1: 전체 백엔드 테스트**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q`
Expected: 전부 PASS.

- [ ] **Step 2: 프론트 빌드** — Run: `cd frontend && npm run build` → 성공.

- [ ] **Step 3: dev 수동 스모크**

백엔드+프론트 dev 구동 후 확인:
- 알림 페이지: 추가(종목 선택 → 기준/방향/값) → 목록 표시 → 켜기/끄기 → 삭제 → (발동된 항목 있으면) 재무장.
- 대시보드/관심종목 행에 알림 배지 표시, 클릭 시 알림 페이지 이동.
- 종목 상세의 알림 폼이 여전히 동작(AlertForm fixed 모드).
- 테마 토글 라이트↔다크 + 새로고침 유지, 창 너비로 사이드바↔탭바 전환.

- [ ] **Step 4: 최종 커밋(필요 시 ROADMAP 갱신)**

`docs/superpowers/ROADMAP.md`에 본 작업 완료 항목 추가 후:
```bash
git add docs/superpowers/ROADMAP.md
git commit -m "docs(roadmap): 알림 허브 + 디자인 시스템 통합 완료 반영"
```

---

## 메모
- 백엔드 신규 표면은 `list_all_alerts_view` + `GET /api/alerts` 선택 파라미터화뿐. 생성/수정/삭제/재무장은 기존 엔드포인트 재사용.
- 포인트색은 `index.css`의 `--accent` 한 곳 → 추후 한 줄 교체로 변경 가능.
- 범위 제외(YAGNI): 알림 발송 이력 페이지, 종목 검색 자동완성, 커스텀 테마색 UI, matplotlib 차트 다크모드, 알림 페이지에서의 값/방향 수정(켜기끄기·삭제·재무장으로 충분).
