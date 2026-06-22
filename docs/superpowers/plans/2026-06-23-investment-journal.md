# 투자저널 (3단계 D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자가 날짜별 자유형 투자 기록(제목·마크다운 본문, 선택적 종목 1개 연결)을 작성·관리하고, 자산 상세에서 종목별 메모를 보고 바로 작성한다.

**Architecture:** 신규 `journal_entries` 테이블 + `/api/journal` 표준 CRUD 라우터(cash 패턴) + 전용 "저널" 페이지(reports/cash 패턴) + AssetDetail "투자 메모" 섹션. 종목 연결은 nullable `asset_id` FK(`ON DELETE SET NULL`).

**Tech Stack:** FastAPI + async SQLAlchemy 2.0 + asyncpg + PostgreSQL, React 18 + Vite + TS. pytest(asyncio).

**테스트 실행 명령(공통):**
```bash
SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q
```

---

## 파일 구조

**백엔드 (신규):**
- `app/models/journal_entry.py` — `JournalEntry` 모델
- `app/schemas/journal.py` — `JournalCreate`, `JournalUpdate`
- `app/routers/journal.py` — `/api/journal` CRUD

**백엔드 (수정):**
- `app/models/__init__.py` — `JournalEntry` 등록
- `app/main.py` — journal 라우터 등록

**프론트 (신규/수정):**
- `frontend/src/pages/Journal.tsx` (신규)
- `frontend/src/api.ts` (수정) — journal 엔드포인트
- `frontend/src/App.tsx` (수정) — `/journal` 라우트
- `frontend/src/components/AppShell.tsx` (수정) — "저널" 메뉴
- `frontend/src/pages/AssetDetail.tsx` (수정) — "투자 메모" 섹션

**테스트 (신규):**
- `tests/test_journal_api.py`

---

## Task 1: JournalEntry 모델 + 테이블

**Files:**
- Create: `app/models/journal_entry.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_journal_api.py`

- [ ] **Step 1: 모델 작성**

`app/models/journal_entry.py`:
```python
from datetime import datetime, date
from sqlalchemy import Text, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets.asset_id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 2: __init__ 등록**

`app/models/__init__.py`에 `from app.models.journal_entry import JournalEntry` 추가(다른 import와 함께)하고 `__all__` 리스트 끝에 `"JournalEntry"` 추가.

- [ ] **Step 3: 테이블 생성 테스트 작성**

`tests/test_journal_api.py` (신규):
```python
import pytest
from sqlalchemy import select
from app.models import JournalEntry


@pytest.mark.asyncio
async def test_journal_entries_table_created(db_session):
    # db_session fixture가 create_all 하므로 빈 조회가 에러 없이 동작하면 테이블 생성됨
    rows = (await db_session.execute(select(JournalEntry))).scalars().all()
    assert rows == []
```

- [ ] **Step 4: 테스트 실행(통과)**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_journal_api.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**
```bash
git add app/models/journal_entry.py app/models/__init__.py tests/test_journal_api.py
git commit -m "feat(journal): journal_entries 모델 + 테이블"
```

---

## Task 2: 스키마 + 라우터 (CRUD) + main 등록

**Files:**
- Create: `app/schemas/journal.py`
- Create: `app/routers/journal.py`
- Modify: `app/main.py`
- Test: `tests/test_journal_api.py`

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_journal_api.py`에 추가(상단에 import 추가: `from httpx import AsyncClient, ASGITransport`, `from app.main import app`, `from app.models import Asset`):
```python
async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _mk_asset() -> Asset:
    return Asset(ticker="TST", name="테스트종목", asset_type="stock",
                 market="KR", currency="KRW", data_source="manual", fetch_symbol="TST")


@pytest.mark.asyncio
async def test_create_defaults_date_and_lists_newest_first(db_session):
    async with await _client() as ac:
        r1 = await ac.post("/api/journal", json={"title": "첫 메모", "body": "본문1"})
        r2 = await ac.post("/api/journal", json={"title": "둘째", "entry_date": "2020-01-01"})
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["title"] == "첫 메모" and body1["asset_id"] is None
    assert body1["entry_date"]  # 서버가 오늘로 채움(빈 문자열 아님)
    async with await _client() as ac:
        lst = (await ac.get("/api/journal")).json()
    # 첫 메모(오늘) > 둘째(2020) → 최신순
    assert [e["title"] for e in lst][:2] == ["첫 메모", "둘째"]


@pytest.mark.asyncio
async def test_create_with_asset_enriches_name(db_session):
    a = _mk_asset()
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    async with await _client() as ac:
        r = await ac.post("/api/journal", json={"title": "종목메모", "asset_id": a.asset_id})
    body = r.json()
    assert body["asset_id"] == a.asset_id
    assert body["asset_name"] == "테스트종목" and body["asset_ticker"] == "TST"


@pytest.mark.asyncio
async def test_create_empty_title_422():
    async with await _client() as ac:
        r = await ac.post("/api/journal", json={"title": "   "})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_invalid_asset_422(db_session):
    async with await _client() as ac:
        r = await ac.post("/api/journal", json={"title": "x", "asset_id": 999999})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_filter_by_asset(db_session):
    a = _mk_asset()
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    async with await _client() as ac:
        await ac.post("/api/journal", json={"title": "연결", "asset_id": a.asset_id})
        await ac.post("/api/journal", json={"title": "비연결"})
        filtered = (await ac.get(f"/api/journal?asset_id={a.asset_id}")).json()
    assert [e["title"] for e in filtered] == ["연결"]


@pytest.mark.asyncio
async def test_update_partial_and_clear_asset(db_session):
    a = _mk_asset()
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    async with await _client() as ac:
        created = (await ac.post("/api/journal", json={"title": "원본", "asset_id": a.asset_id})).json()
        upd = (await ac.put(f"/api/journal/{created['id']}",
                            json={"title": "수정됨", "asset_id": None})).json()
    assert upd["title"] == "수정됨" and upd["asset_id"] is None and upd["asset_name"] is None


@pytest.mark.asyncio
async def test_get_and_delete_and_404(db_session):
    async with await _client() as ac:
        created = (await ac.post("/api/journal", json={"title": "삭제대상"})).json()
        got = await ac.get(f"/api/journal/{created['id']}")
        assert got.status_code == 200
        dele = await ac.delete(f"/api/journal/{created['id']}")
        assert dele.status_code == 200
        assert (await ac.get(f"/api/journal/{created['id']}")).status_code == 404
        assert (await ac.put(f"/api/journal/{created['id']}", json={"title": "x"})).status_code == 404
        assert (await ac.delete(f"/api/journal/{created['id']}")).status_code == 404


@pytest.mark.asyncio
async def test_asset_delete_sets_null(db_session):
    a = _mk_asset()
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    async with await _client() as ac:
        created = (await ac.post("/api/journal", json={"title": "보존", "asset_id": a.asset_id})).json()
    await db_session.delete(a)
    await db_session.commit()
    async with await _client() as ac:
        got = (await ac.get(f"/api/journal/{created['id']}")).json()
    assert got["asset_id"] is None and got["title"] == "보존"
```

> 주의: 이 테스트들은 `db_session` fixture(스키마 준비)와 ASGI 클라이언트(앱은 `SessionLocal`로 자체 세션 사용)를 함께 쓴다. 둘 다 같은 `invest_test` 스키마를 가리키므로, fixture가 만든 Asset 행을 앱 라우터가 읽을 수 있다. `db_session`을 인자로 받아야 스키마가 준비되고 테스트 간 TRUNCATE 격리가 적용된다.

- [ ] **Step 2: 실패 확인**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_journal_api.py::test_create_defaults_date_and_lists_newest_first -v`
Expected: FAIL (404 — 라우터 없음)

- [ ] **Step 3: 스키마 작성**

`app/schemas/journal.py`:
```python
from datetime import date
from pydantic import BaseModel


class JournalCreate(BaseModel):
    title: str
    body: str | None = None
    asset_id: int | None = None
    entry_date: date | None = None


class JournalUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    asset_id: int | None = None
    entry_date: date | None = None
```

- [ ] **Step 4: 라우터 작성**

`app/routers/journal.py`:
```python
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import JournalEntry, Asset
from app.schemas.journal import JournalCreate, JournalUpdate

router = APIRouter(prefix="/api/journal", tags=["journal"])
_KST = ZoneInfo("Asia/Seoul")


async def _asset_map(db: AsyncSession, asset_ids) -> dict:
    ids = {i for i in asset_ids if i is not None}
    if not ids:
        return {}
    rows = (await db.execute(select(Asset).where(Asset.asset_id.in_(ids)))).scalars().all()
    return {a.asset_id: (a.name, a.ticker) for a in rows}


def _serialize(e: JournalEntry, amap: dict) -> dict:
    name, ticker = amap.get(e.asset_id, (None, None))
    return {
        "id": e.id, "entry_date": e.entry_date.isoformat(),
        "title": e.title, "body": e.body, "asset_id": e.asset_id,
        "asset_name": name, "asset_ticker": ticker,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


async def _validate_asset(db: AsyncSession, asset_id) -> None:
    if asset_id is not None and await db.get(Asset, asset_id) is None:
        raise HTTPException(422, "연결할 종목을 찾을 수 없습니다.")


@router.post("")
async def create_entry(body: JournalCreate, db: AsyncSession = Depends(get_db)):
    if not body.title or not body.title.strip():
        raise HTTPException(422, "title은 비울 수 없습니다.")
    await _validate_asset(db, body.asset_id)
    entry = JournalEntry(
        entry_date=body.entry_date or datetime.now(_KST).date(),
        title=body.title, body=body.body, asset_id=body.asset_id)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _serialize(entry, await _asset_map(db, [entry.asset_id]))


@router.get("")
async def list_entries(asset_id: int | None = Query(None), db: AsyncSession = Depends(get_db)):
    stmt = select(JournalEntry).order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
    if asset_id is not None:
        stmt = stmt.where(JournalEntry.asset_id == asset_id)
    entries = (await db.execute(stmt)).scalars().all()
    amap = await _asset_map(db, [e.asset_id for e in entries])
    return [_serialize(e, amap) for e in entries]


@router.get("/{entry_id}")
async def get_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    e = await db.get(JournalEntry, entry_id)
    if e is None:
        raise HTTPException(404, "저널 항목을 찾을 수 없습니다.")
    return _serialize(e, await _asset_map(db, [e.asset_id]))


@router.put("/{entry_id}")
async def update_entry(entry_id: int, body: JournalUpdate, db: AsyncSession = Depends(get_db)):
    e = await db.get(JournalEntry, entry_id)
    if e is None:
        raise HTTPException(404, "저널 항목을 찾을 수 없습니다.")
    data = body.model_dump(exclude_unset=True)
    if "title" in data and (not data["title"] or not data["title"].strip()):
        raise HTTPException(422, "title은 비울 수 없습니다.")
    if "asset_id" in data:
        await _validate_asset(db, data["asset_id"])
    for k, v in data.items():
        setattr(e, k, v)
    await db.commit()
    await db.refresh(e)
    return _serialize(e, await _asset_map(db, [e.asset_id]))


@router.delete("/{entry_id}")
async def delete_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    e = await db.get(JournalEntry, entry_id)
    if e is None:
        raise HTTPException(404, "저널 항목을 찾을 수 없습니다.")
    await db.delete(e)
    await db.commit()
    return {"deleted": entry_id}
```

- [ ] **Step 5: main.py 등록**

`app/main.py`:
- `from app.routers import ...` 줄에 `journal` 추가.
- `for r in (...)` include 튜플에 `journal.router` 추가.
Read 후 두 곳 정확히 수정.

- [ ] **Step 6: 통과 확인**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest tests/test_journal_api.py -v`
Expected: PASS (전체)

- [ ] **Step 7: 커밋**
```bash
git add app/schemas/journal.py app/routers/journal.py app/main.py tests/test_journal_api.py
git commit -m "feat(journal): /api/journal CRUD 라우터 + 등록"
```

---

## Task 3: 프론트엔드 — 저널 페이지 + 메뉴

**Files:**
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/pages/Journal.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`

- [ ] **Step 1: api.ts에 엔드포인트 + 타입 추가**

`frontend/src/api.ts`의 `api` 객체에 추가:
```typescript
  listJournal: (assetId?: number) =>
    j<JournalEntry[]>(`/api/journal${assetId != null ? `?asset_id=${assetId}` : ""}`),
  getJournal: (id: number) => j<JournalEntry>(`/api/journal/${id}`),
  createJournal: (e: { title: string; body?: string; asset_id?: number | null; entry_date?: string }) =>
    j<JournalEntry>("/api/journal", { method: "POST", body: JSON.stringify(e) }),
  updateJournal: (id: number, e: { title?: string; body?: string; asset_id?: number | null; entry_date?: string }) =>
    j<JournalEntry>(`/api/journal/${id}`, { method: "PUT", body: JSON.stringify(e) }),
  deleteJournal: (id: number) => j(`/api/journal/${id}`, { method: "DELETE" }),
```
타입 선언 추가(다른 타입 옆):
```typescript
export type JournalEntry = {
  id: number; entry_date: string; title: string; body: string | null;
  asset_id: number | null; asset_name: string | null; asset_ticker: string | null;
  created_at: string | null; updated_at: string | null;
};
```
종목 드롭다운용 자산 목록은 기존 `api.listAssets()`(활성 자산 배열)를 재사용한다 — 새 메서드 만들지 말 것.

- [ ] **Step 2: Journal.tsx 작성**

`frontend/src/pages/Journal.tsx`:
```tsx
import { useEffect, useState } from "react";
import { api, JournalEntry } from "../api";

export default function Journal() {
  const [rows, setRows] = useState<JournalEntry[]>([]);
  const [assets, setAssets] = useState<any[]>([]);
  const [form, setForm] = useState({ entry_date: "", title: "", body: "", asset_id: "" });
  const [editing, setEditing] = useState<number | null>(null);
  const [edit, setEdit] = useState({ title: "", body: "", asset_id: "" });
  const [error, setError] = useState("");

  const load = async () => {
    try { setRows(await api.listJournal()); } catch (e) { setError(String(e)); }
  };
  useEffect(() => {
    load();
    api.listAssets().then(setAssets).catch(() => setAssets([]));
  }, []);

  const create = async () => {
    setError("");
    if (!form.title.trim()) { setError("제목을 입력하세요."); return; }
    try {
      await api.createJournal({
        title: form.title, body: form.body || undefined,
        asset_id: form.asset_id ? Number(form.asset_id) : null,
        entry_date: form.entry_date || undefined,
      });
      setForm({ entry_date: "", title: "", body: "", asset_id: "" });
      await load();
    } catch (e) { setError(String(e)); }
  };

  const startEdit = (r: JournalEntry) => {
    setEditing(r.id);
    setEdit({ title: r.title, body: r.body ?? "", asset_id: r.asset_id != null ? String(r.asset_id) : "" });
  };
  const saveEdit = async (id: number) => {
    try {
      await api.updateJournal(id, {
        title: edit.title, body: edit.body,
        asset_id: edit.asset_id ? Number(edit.asset_id) : null,
      });
      setEditing(null);
      await load();
    } catch (e) { setError(String(e)); }
  };
  const remove = async (id: number) => { await api.deleteJournal(id); await load(); };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">투자 저널</h1>
      {error && <div className="card text-sm" style={{ color: "var(--down)" }}>{error}</div>}

      <section className="card space-y-2">
        <h2 className="font-semibold">새 기록</h2>
        <div className="flex flex-wrap gap-2">
          <input className="input" type="date" value={form.entry_date}
                 onChange={(e) => setForm({ ...form, entry_date: e.target.value })} />
          <select className="input" value={form.asset_id}
                  onChange={(e) => setForm({ ...form, asset_id: e.target.value })}>
            <option value="">연결 안 함</option>
            {assets.map((a) => (
              <option key={a.asset_id} value={a.asset_id}>{a.name} ({a.ticker})</option>
            ))}
          </select>
        </div>
        <input className="input w-full" placeholder="제목" value={form.title}
               onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <textarea className="input w-full h-28" placeholder="본문(마크다운)" value={form.body}
                  onChange={(e) => setForm({ ...form, body: e.target.value })} />
        <button className="btn btn-primary" onClick={create}>저장</button>
      </section>

      <div className="space-y-2">
        {rows.length === 0 && <p className="text-sm text-muted">아직 기록이 없습니다.</p>}
        {rows.map((r) => (
          <div key={r.id} className="card space-y-1">
            {editing === r.id ? (
              <div className="space-y-2">
                <input className="input w-full" value={edit.title}
                       onChange={(e) => setEdit({ ...edit, title: e.target.value })} />
                <textarea className="input w-full h-28" value={edit.body}
                          onChange={(e) => setEdit({ ...edit, body: e.target.value })} />
                <select className="input" value={edit.asset_id}
                        onChange={(e) => setEdit({ ...edit, asset_id: e.target.value })}>
                  <option value="">연결 안 함</option>
                  {assets.map((a) => (
                    <option key={a.asset_id} value={a.asset_id}>{a.name} ({a.ticker})</option>
                  ))}
                </select>
                <div className="flex gap-2">
                  <button className="btn btn-primary" onClick={() => saveEdit(r.id)}>저장</button>
                  <button className="btn" onClick={() => setEditing(null)}>취소</button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <div className="text-sm">
                    <span className="text-muted">{r.entry_date}</span>{" "}
                    <span className="font-semibold">{r.title}</span>{" "}
                    {r.asset_name && <span className="badge">{r.asset_name} ({r.asset_ticker})</span>}
                  </div>
                  <div className="flex gap-2">
                    <button className="btn btn-ghost text-xs" onClick={() => startEdit(r)}>수정</button>
                    <button className="btn btn-ghost text-xs" onClick={() => remove(r.id)}>삭제</button>
                  </div>
                </div>
                {r.body && <div className="whitespace-pre-wrap text-sm">{r.body}</div>}
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```
> 클래스명(`card`/`btn`/`btn-primary`/`btn-ghost`/`input`/`badge`/`text-muted`)은 기존 페이지에서 쓰는 것. 없으면 가장 가까운 기존 클래스로 대체.

- [ ] **Step 3: App.tsx 라우트 추가**

`frontend/src/App.tsx`: `import Journal from "./pages/Journal";` 추가, `<Routes>` 안에 `<Route path="/journal" element={<Journal />} />` 추가.

- [ ] **Step 4: AppShell.tsx 메뉴 추가**

`frontend/src/components/AppShell.tsx` nav 배열에서 "리포트"와 "설정" 사이에 추가:
```tsx
  { to: "/journal", label: "저널" },
```

- [ ] **Step 5: 빌드·타입체크**

Run: `cd frontend && npm run build`
Expected: 성공(타입 에러 0). `JournalEntry`는 `import type` 규칙(verbatimModuleSyntax)에 맞춰 import해야 할 수 있다 — 빌드 에러 시 `import { api, type JournalEntry }`로 조정.

- [ ] **Step 6: 커밋**
```bash
git add frontend/src/api.ts frontend/src/pages/Journal.tsx frontend/src/App.tsx frontend/src/components/AppShell.tsx
git commit -m "feat(journal): 저널 페이지·메뉴(프론트)"
```

---

## Task 4: AssetDetail "투자 메모" 섹션

**Files:**
- Modify: `frontend/src/pages/AssetDetail.tsx`

- [ ] **Step 1: 상태 + 로딩 추가**

`frontend/src/pages/AssetDetail.tsx`의 컴포넌트 상단 useState들 옆에 추가:
```tsx
const [journal, setJournal] = useState<JournalEntry[]>([]);
const [jForm, setJForm] = useState({ title: "", body: "" });
const [jMsg, setJMsg] = useState("");
```
import에 타입 추가: 파일 상단 api import에 `JournalEntry`를 포함(예: `import { api, type JournalEntry } from "../api";` — 기존 import 형태에 맞춰 추가).
기존 `useEffect`(assetId 의존)의 본문에 로딩 추가:
```tsx
api.listJournal(assetId).then(setJournal).catch(() => setJournal([]));
```

- [ ] **Step 2: 작성 핸들러 추가**

컴포넌트 내 다른 핸들러 옆에 추가:
```tsx
const addJournal = async () => {
  if (!assetId || !jForm.title.trim()) { setJMsg("제목을 입력하세요."); return; }
  try {
    await api.createJournal({ asset_id: assetId, title: jForm.title, body: jForm.body || undefined });
    setJForm({ title: "", body: "" });
    setJMsg("저장됨");
    setJournal(await api.listJournal(assetId));
  } catch (e) { setJMsg(String(e)); }
};
const removeJournal = async (jid: number) => {
  await api.deleteJournal(jid);
  if (assetId) setJournal(await api.listJournal(assetId));
};
```

- [ ] **Step 3: JSX 섹션 추가**

다른 섹션들(예: "가격 알림") 근처에 추가:
```tsx
<section className="card space-y-2">
  <h2 className="font-semibold text-muted">투자 메모</h2>
  <input className="input w-full" placeholder="제목" value={jForm.title}
         onChange={(e) => setJForm({ ...jForm, title: e.target.value })} />
  <textarea className="input w-full h-24" placeholder="이 종목에 대한 메모(마크다운)" value={jForm.body}
            onChange={(e) => setJForm({ ...jForm, body: e.target.value })} />
  <div className="flex items-center gap-2">
    <button className="btn btn-primary" onClick={addJournal}>메모 추가</button>
    {jMsg && <span className="text-sm text-muted">{jMsg}</span>}
  </div>
  <div className="space-y-1">
    {journal.length === 0 && <p className="text-sm text-muted">이 종목에 대한 메모가 없습니다.</p>}
    {journal.map((e) => (
      <div key={e.id} className="border-t pt-1" style={{ borderColor: "var(--border)" }}>
        <div className="flex items-center justify-between">
          <span className="text-sm"><span className="text-muted">{e.entry_date}</span> <span className="font-semibold">{e.title}</span></span>
          <button className="btn btn-ghost text-xs" onClick={() => removeJournal(e.id)}>삭제</button>
        </div>
        {e.body && <div className="whitespace-pre-wrap text-sm">{e.body}</div>}
      </div>
    ))}
  </div>
</section>
```

- [ ] **Step 4: 빌드·타입체크**

Run: `cd frontend && npm run build`
Expected: 성공.

- [ ] **Step 5: 커밋**
```bash
git add frontend/src/pages/AssetDetail.tsx
git commit -m "feat(journal): 자산 상세 '투자 메모' 섹션(읽기+빠른작성)"
```

---

## Task 5: 최종 검증 + 로드맵

**Files:**
- Modify: `docs/superpowers/ROADMAP.md`

- [ ] **Step 1: 백엔드 전체 테스트**

Run: `SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q`
Expected: 전부 PASS(기존 234 + 신규 약 9 = 약 243). 실패 0. (간헐 네트워크 오류 시 해당 파일 격리 재실행으로 확인.)

- [ ] **Step 2: 프론트 빌드**

Run: `cd frontend && npm run build`
Expected: 성공.

- [ ] **Step 3: ROADMAP에 3단계 D 완료 + 3단계 종료 반영**

`docs/superpowers/ROADMAP.md`: "### 3단계 D — 미착수"를 "구현 완료 (2026-06-23)"로 갱신(spec/plan 경로·테스트 수 기록). 상단 헤더 "(A·B·C 완료)"를 "(A·B·C·D 완료 — 3단계 종료)"로 갱신.

- [ ] **Step 4: 커밋**
```bash
git add docs/superpowers/ROADMAP.md
git commit -m "docs(roadmap): 3단계 D 투자저널 완료 반영(3단계 종료)"
```

> **수동 스모크(사용자 확인 대기)**: 저널 페이지에서 기록 작성/수정/삭제, 종목 연결 → 자산 상세 "투자 메모"에 노출·빠른작성 확인.

---

## Self-Review (작성자 확인 완료)

- **스펙 커버리지**: 자유형 항목(date/title/body)=모델(T1)·스키마(T2) / 종목 연결 nullable+SET NULL=모델(T1)·테스트(T2) / CRUD+필터+검증+enrich=라우터(T2) / 기본 날짜 KST=라우터(T2) / 저널 페이지+메뉴=프론트(T3) / AssetDetail 읽기+빠른작성=프론트(T4) / 레거시 미마이그레이션=설계대로(테이블 신규) / 에러(title 422·asset 422·404)=T2. 모두 매핑.
- **플레이스홀더**: 없음(모든 코드 실내용).
- **타입 일관성**: `JournalEntry`(모델)·`JournalCreate/Update`(스키마)·`_serialize` 출력키(id/entry_date/title/body/asset_id/asset_name/asset_ticker/created_at/updated_at) ↔ 프론트 `JournalEntry` 타입 ↔ api 메서드 시그니처 일치. `ON DELETE SET NULL`은 신규 DB(ensure_schema)에 자동 반영(기존 DB 없음 — 신규 테이블).
