# 변동성(REFERENCE) 알림 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 가격 알림에 트레일링 반복 변동률 기준(`REFERENCE`)을 추가해, 기준가 대비 ±X% 변동 시 양방향(급등·급락) 알림을 보내고 기준가를 재설정해 계속 감시한다.

**Architecture:** 기존 `PriceAlert` 모델에 `reference_price` 컬럼과 `REFERENCE` basis를 추가한다. 5분 tick 디스패처에 REFERENCE 분기(lazy-init → ±X% 발동 → 기준가 재설정, `is_triggered` 불변)를 넣고, 텔레그램·장중 게이팅·알림 허브·배지를 재사용한다. 순수 평가함수 `ref_fired`로 양방향 임계 판정을 분리한다.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, PostgreSQL(invest 스키마), pytest(invest_test 격리 스키마), React 18 + Vite + TS.

설계 spec: `docs/superpowers/specs/2026-06-20-volatility-reference-alert-design.md`

테스트 실행(격리 스키마):
```
SCHEMA_NAME=invest_test TEST_DATABASE_URL='postgresql+asyncpg://ai_agent:mook123!@100.114.126.67:5432/agent_db' .venv/bin/pytest -q
```
(이하 플랜에서 `PYTEST` = 위 환경변수 프리픽스 + `.venv/bin/pytest`)

## File Structure

- `app/models/price_alert.py` — `reference_price` 컬럼 추가.
- `app/services/alert/evaluator.py` — 순수 `ref_fired()` 추가.
- `app/services/alert/message.py` — `_BASIS_LABEL["REFERENCE"]` + `build_reference_message()`.
- `app/services/alert/alert_dispatcher.py` — REFERENCE 분기.
- `app/services/alert/alert_store.py` — `_alert_row`에 `reference_price`/REFERENCE 계산.
- `app/schemas/alert.py` — `Basis`/`Direction` Literal 확장, `AlertOut.reference_price`.
- `app/routers/alerts.py` — REFERENCE 생성 시 `direction="BOTH"` 정규화.
- `frontend/src/api.ts` — 타입 확장.
- `frontend/src/components/AlertForm.tsx` — REFERENCE 옵션 + 방향 숨김.
- `frontend/src/pages/Alerts.tsx`, `frontend/src/pages/AssetDetail.tsx` — 밴드 표시.
- 테스트: `tests/test_alert_evaluator.py`, `tests/test_alert_message.py`, `tests/test_alert_dispatcher.py`, `tests/test_alert_store.py`, `tests/test_alerts_api.py`.

---

### Task 1: 모델 + 스키마에 reference_price/REFERENCE 추가

**Files:**
- Modify: `app/models/price_alert.py`
- Modify: `app/schemas/alert.py`

- [ ] **Step 1: 모델에 컬럼 추가**

`app/models/price_alert.py`의 `value` 컬럼 바로 아래(현재 line 15 다음)에 추가:

```python
    reference_price: Mapped[float | None] = mapped_column(Numeric)   # REFERENCE 트레일링 기준가
```

`direction` 컬럼 주석은 `# ABOVE/BELOW/BOTH(REFERENCE)`로 갱신, `basis` 주석에 `/REFERENCE` 추가.

- [ ] **Step 2: 스키마 Literal 확장**

`app/schemas/alert.py` 상단 두 Literal을 교체:

```python
Basis = Literal["ABSOLUTE", "PURCHASE_AVG", "WEEK52_HIGH", "WEEK52_LOW", "REFERENCE"]
Direction = Literal["ABOVE", "BELOW", "BOTH"]
```

`AlertOut`에 필드 추가(`note` 위/아래 아무 곳, `model_config` 위):

```python
    reference_price: float | None = None
```

- [ ] **Step 3: import 확인 후 커밋**

Run: `.venv/bin/python -c "import app.models.price_alert, app.schemas.alert"`
Expected: 에러 없음(종료코드 0)

```bash
git add app/models/price_alert.py app/schemas/alert.py
git commit -m "feat(alerts): PriceAlert.reference_price 컬럼 + REFERENCE/BOTH Literal"
```

---

### Task 2: 순수 평가함수 ref_fired

**Files:**
- Modify: `app/services/alert/evaluator.py`
- Test: `tests/test_alert_evaluator.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_alert_evaluator.py` 맨 위 import를 교체하고 파일 끝에 테스트 추가:

```python
from app.services.alert.evaluator import compute_target, is_fired, ref_fired
```

```python
def test_ref_fired_up_threshold():
    assert ref_fired(100.0, 105.0, 5.0) is True     # +5% 경계 도달
    assert ref_fired(100.0, 104.9, 5.0) is False

def test_ref_fired_down_threshold():
    assert ref_fired(100.0, 95.0, 5.0) is True       # -5% 경계 도달(양방향)
    assert ref_fired(100.0, 96.0, 5.0) is False

def test_ref_fired_zero_reference_guard():
    assert ref_fired(0.0, 100.0, 5.0) is False
```

- [ ] **Step 2: 실패 확인**

Run: `PYTEST tests/test_alert_evaluator.py -q`
Expected: FAIL — `ImportError: cannot import name 'ref_fired'`

- [ ] **Step 3: 구현**

`app/services/alert/evaluator.py` 끝에 추가:

```python
def ref_fired(reference_price: float, current_price: float, value: float) -> bool:
    """기준가 대비 |변동률| >= value(%) 이면 True. 양방향, 경계 포함."""
    if reference_price <= 0:
        return False
    change_pct = abs((current_price - reference_price) / reference_price) * 100.0
    return change_pct >= value
```

- [ ] **Step 4: 통과 확인**

Run: `PYTEST tests/test_alert_evaluator.py -q`
Expected: PASS (전체)

- [ ] **Step 5: 커밋**

```bash
git add app/services/alert/evaluator.py tests/test_alert_evaluator.py
git commit -m "feat(alerts): ref_fired 양방향 변동률 판정 순수함수"
```

---

### Task 3: REFERENCE 텔레그램 메시지

**Files:**
- Modify: `app/services/alert/message.py`
- Test: `tests/test_alert_message.py`

- [ ] **Step 1: 실패하는 테스트 작성**

먼저 `tests/test_alert_message.py`의 import 라인(line 2)을 교체:

```python
from app.services.alert.message import build_message, build_reference_message
```

파일 끝에 테스트 추가(기존 `_asset`/`SimpleNamespace` 재사용):

```python
def test_reference_message_up():
    a = SimpleNamespace(basis="REFERENCE", direction="BOTH", value=5.0)
    msg = build_reference_message(_asset(), a, current_price=105.0, reference_price=100.0)
    assert "변동률 감시" in msg
    assert "상승" in msg
    assert "+5.00%" in msg

def test_reference_message_down():
    a = SimpleNamespace(basis="REFERENCE", direction="BOTH", value=5.0)
    msg = build_reference_message(_asset(), a, current_price=94.0, reference_price=100.0)
    assert "하락" in msg
    assert "-6.00%" in msg
```

- [ ] **Step 2: 실패 확인**

Run: `PYTEST tests/test_alert_message.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_reference_message'`

- [ ] **Step 3: 구현**

`app/services/alert/message.py`의 `_BASIS_LABEL` 딕셔너리에 항목 추가:

```python
    "REFERENCE": "변동률 감시",
```

파일 끝에 함수 추가:

```python
def build_reference_message(asset, alert, current_price: float, reference_price: float) -> str:
    change_pct = (current_price - reference_price) / reference_price * 100.0
    direction = "상승" if change_pct >= 0 else "하락"
    return (
        f"🔔 <b>{asset.name}</b> ({asset.ticker}·{asset.market})\n"
        f"조건: {_BASIS_LABEL['REFERENCE']} ±{float(alert.value):g}%\n"
        f"급격한 {direction}! 기준가 {_fmt(reference_price, asset.currency)} → "
        f"현재가 {_fmt(current_price, asset.currency)} ({change_pct:+.2f}%)"
    )
```

- [ ] **Step 4: 통과 확인**

Run: `PYTEST tests/test_alert_message.py -q`
Expected: PASS (전체)

- [ ] **Step 5: 커밋**

```bash
git add app/services/alert/message.py tests/test_alert_message.py
git commit -m "feat(alerts): REFERENCE 변동률 텔레그램 메시지 빌더"
```

---

### Task 4: 디스패처 REFERENCE 분기

**Files:**
- Modify: `app/services/alert/alert_dispatcher.py`
- Test: `tests/test_alert_dispatcher.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_alert_dispatcher.py`의 `_alert` 헬퍼에 `reference_price=None` 기본 필드를 추가하도록 교체:

```python
def _alert(alert_id=1, basis="ABSOLUTE", direction="ABOVE", value=100.0, reference_price=None):
    return SimpleNamespace(alert_id=alert_id, basis=basis, direction=direction, value=value,
                           enabled=True, is_triggered=False, triggered_at=None,
                           last_notified_at=None, reference_price=reference_price)
```

파일 끝에 테스트 3개 추가:

```python
@pytest.mark.asyncio
async def test_reference_lazy_init_sets_reference_no_fire():
    asset = _asset()
    alert = _alert(basis="REFERENCE", direction="BOTH", value=5.0, reference_price=None)
    q = Quote(price=100.0, currency="USD", status="ok")
    send = AsyncMock(return_value=True)
    with patch.object(disp, "SessionLocal", return_value=_FakeSession()), \
         patch.object(disp.alert_store, "list_active_with_assets", AsyncMock(return_value=[(alert, asset)])), \
         patch.object(disp, "is_market_open", return_value=True), \
         patch.object(disp, "get_quote", AsyncMock(return_value=q)), \
         patch.object(disp.telegram_service, "send_message", send), \
         patch.object(disp.asyncio, "sleep", AsyncMock()):
        await disp.evaluate_tick()
    assert alert.reference_price == 100.0
    send.assert_not_awaited()
    assert alert.is_triggered is False

@pytest.mark.asyncio
async def test_reference_fires_and_reanchors():
    asset = _asset()
    alert = _alert(basis="REFERENCE", direction="BOTH", value=5.0, reference_price=100.0)
    q = Quote(price=106.0, currency="USD", status="ok")
    send = AsyncMock(return_value=True)
    with patch.object(disp, "SessionLocal", return_value=_FakeSession()), \
         patch.object(disp.alert_store, "list_active_with_assets", AsyncMock(return_value=[(alert, asset)])), \
         patch.object(disp, "is_market_open", return_value=True), \
         patch.object(disp, "get_quote", AsyncMock(return_value=q)), \
         patch.object(disp.telegram_service, "send_message", send), \
         patch.object(disp.asyncio, "sleep", AsyncMock()):
        await disp.evaluate_tick()
    send.assert_awaited_once()
    assert alert.reference_price == 106.0     # 재설정
    assert alert.enabled is True              # 유지
    assert alert.is_triggered is False        # 불변
    assert alert.last_notified_at is not None

@pytest.mark.asyncio
async def test_reference_below_threshold_no_fire():
    asset = _asset()
    alert = _alert(basis="REFERENCE", direction="BOTH", value=5.0, reference_price=100.0)
    q = Quote(price=103.0, currency="USD", status="ok")
    send = AsyncMock(return_value=True)
    with patch.object(disp, "SessionLocal", return_value=_FakeSession()), \
         patch.object(disp.alert_store, "list_active_with_assets", AsyncMock(return_value=[(alert, asset)])), \
         patch.object(disp, "is_market_open", return_value=True), \
         patch.object(disp, "get_quote", AsyncMock(return_value=q)), \
         patch.object(disp.telegram_service, "send_message", send), \
         patch.object(disp.asyncio, "sleep", AsyncMock()):
        await disp.evaluate_tick()
    send.assert_not_awaited()
    assert alert.reference_price == 100.0
```

- [ ] **Step 2: 실패 확인**

Run: `PYTEST tests/test_alert_dispatcher.py -q`
Expected: FAIL — REFERENCE 분기 없어 `send`가 호출되거나 `reference_price` 미설정으로 assert 실패

- [ ] **Step 3: 구현**

`app/services/alert/alert_dispatcher.py` 상단 import에 `ref_fired`와 `build_reference_message` 추가:

```python
from app.services.alert.evaluator import compute_target, is_fired, ref_fired
from app.services.alert.message import build_message, build_reference_message
```

내부 `for alert in alerts:` 루프(현재 line 39~59)를 아래로 교체:

```python
            for alert in alerts:
                try:
                    if alert.basis == "REFERENCE":
                        if alert.reference_price is None:
                            alert.reference_price = quote.price
                            await db.commit()
                            continue
                        if not ref_fired(float(alert.reference_price), quote.price, float(alert.value)):
                            continue
                        msg = build_reference_message(asset, alert, quote.price, float(alert.reference_price))
                    else:
                        basis_price = await resolve_basis_price(db, asset, alert.basis)
                        if basis_price is None and alert.basis != "ABSOLUTE":
                            continue
                        target = compute_target(alert.basis, alert.direction, float(alert.value), basis_price)
                        if not is_fired(alert.direction, quote.price, target):
                            continue
                        msg = build_message(asset, alert, quote.price, target)
                    try:
                        ok = await telegram_service.send_message(db, msg)
                    except telegram_service.TelegramNotConfigured:
                        _log.info("텔레그램 미설정 — 알림 발송 생략")
                        return
                    if ok:
                        if alert.basis == "REFERENCE":
                            alert.reference_price = quote.price
                            alert.last_notified_at = now
                        else:
                            alert.enabled = False
                            alert.is_triggered = True
                            alert.triggered_at = now
                            alert.last_notified_at = now
                        await db.commit()
                    await asyncio.sleep(2)   # 텔레그램 rate-limit 여유
                except Exception as e:   # noqa: BLE001 — 한 건 실패가 나머지를 막지 않게
                    await db.rollback()
                    _log.warning("알림 평가 실패 alert_id=%s: %s", alert.alert_id, e)
```

- [ ] **Step 4: 통과 확인**

Run: `PYTEST tests/test_alert_dispatcher.py -q`
Expected: PASS (신규 3 + 기존 회귀 전부)

- [ ] **Step 5: 커밋**

```bash
git add app/services/alert/alert_dispatcher.py tests/test_alert_dispatcher.py
git commit -m "feat(alerts): 디스패처 REFERENCE 트레일링 분기(발동 후 기준가 재설정)"
```

---

### Task 5: 알림 뷰에 reference_price/REFERENCE 계산

**Files:**
- Modify: `app/services/alert/alert_store.py`
- Test: `tests/test_alert_store.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_alert_store.py` 끝에 추가(기존 `db_session` 실DB 픽스처 + `_asset`/`alert_store` 재사용). `_alert_row`를 직접 호출:

```python
@pytest.mark.asyncio
async def test_alert_row_reference_includes_reference_price(db_session):
    a = _asset(ticker="REF", fetch_symbol="REF")
    db_session.add(a); await db_session.commit()
    alert = PriceAlert(asset_id=a.asset_id, basis="REFERENCE", direction="BOTH", value=5.0)
    alert.reference_price = 100.0
    db_session.add(alert); await db_session.commit()
    row = await alert_store._alert_row(db_session, a, alert, 106.0, "ok")
    assert row["reference_price"] == 100.0
    assert row["target_price"] is None
    assert row["fired"] is True            # |6%| >= 5%

@pytest.mark.asyncio
async def test_alert_row_non_reference_reference_price_none(db_session):
    a = _asset(ticker="NREF", fetch_symbol="NREF")
    db_session.add(a); await db_session.commit()
    alert = PriceAlert(asset_id=a.asset_id, basis="ABSOLUTE", direction="ABOVE", value=200.0)
    db_session.add(alert); await db_session.commit()
    row = await alert_store._alert_row(db_session, a, alert, 150.0, "ok")
    assert row["reference_price"] is None
    assert row["target_price"] == 200.0
```

- [ ] **Step 2: 실패 확인**

Run: `PYTEST tests/test_alert_store.py -q`
Expected: FAIL — `KeyError: 'reference_price'` 또는 REFERENCE에서 `fired` 오판정

- [ ] **Step 3: 구현**

`app/services/alert/alert_store.py` 상단 import(line 80 부근)에 `ref_fired` 추가:

```python
from app.services.alert.evaluator import compute_target, is_fired, ref_fired
```

`_alert_row`(현재 line 83~97)를 교체:

```python
async def _alert_row(db: AsyncSession, asset: Asset, a: PriceAlert, cur: float | None,
                     price_status: str) -> dict:
    """단일 알림 + 라이브(목표가·발동여부) 계산. cur는 자산 현재가(없으면 None)."""
    ref = float(a.reference_price) if a.reference_price is not None else None
    if a.basis == "REFERENCE":
        target = None
        fired = bool(cur is not None and ref is not None
                     and ref_fired(ref, cur, float(a.value)))
    else:
        bp = await resolve_basis_price(db, asset, a.basis)
        target = (compute_target(a.basis, a.direction, float(a.value), bp)
                  if (bp is not None or a.basis == "ABSOLUTE") else None)
        fired = bool(cur is not None and target is not None
                     and is_fired(a.direction, cur, target))
    return {
        "alert_id": a.alert_id, "asset_id": a.asset_id, "basis": a.basis,
        "direction": a.direction, "value": float(a.value), "enabled": a.enabled,
        "is_triggered": a.is_triggered, "note": a.note,
        "target_price": target, "reference_price": ref, "current_price": cur,
        "price_status": price_status, "fired": fired,
    }
```

- [ ] **Step 4: 통과 확인**

Run: `PYTEST tests/test_alert_store.py -q`
Expected: PASS (신규 + 기존 회귀)

- [ ] **Step 5: 커밋**

```bash
git add app/services/alert/alert_store.py tests/test_alert_store.py
git commit -m "feat(alerts): 알림 뷰에 reference_price + REFERENCE fired 계산"
```

---

### Task 6: 라우터 REFERENCE 생성/검증

**Files:**
- Modify: `app/routers/alerts.py`
- Test: `tests/test_alerts_api.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_alerts_api.py` 끝에 추가(기존 mock 스타일 — `_client()`, `patch("app.db.AsyncSession.get", ...)`, `_real_alert()` 재사용):

```python
@pytest.mark.asyncio
async def test_create_reference_normalizes_direction_to_both():
    asset = MagicMock(data_source="yfinance")
    created = _real_alert()
    created.basis = "REFERENCE"
    created.direction = "BOTH"
    with patch("app.db.AsyncSession.get", AsyncMock(return_value=asset)), \
         patch("app.routers.alerts.alert_store.create_alert", AsyncMock(return_value=created)) as ca:
        async with await _client() as ac:
            resp = await ac.post("/api/alerts", json={
                "asset_id": 1, "basis": "REFERENCE", "direction": "ABOVE", "value": 5})
    assert resp.status_code == 200
    assert resp.json()["basis"] == "REFERENCE"
    # 라우터가 REFERENCE면 store에 direction="BOTH"로 전달(요청의 ABOVE 무시)
    assert ca.await_args.args[3] == "BOTH"

@pytest.mark.asyncio
async def test_create_reference_rejects_nonpositive_value():
    async with await _client() as ac:
        resp = await ac.post("/api/alerts", json={
            "asset_id": 1, "basis": "REFERENCE", "direction": "BOTH", "value": 0})
    assert resp.status_code == 422
```

(`create_alert` 호출은 `create_alert(db, asset_id, basis, direction, value, note)` 순서라 `await_args.args[3]`이 direction이다. 두 번째 테스트는 pydantic value>0 검증이 basis 무관하게 동작함을 확인 — `AsyncSession.get` 도달 전 422.)

- [ ] **Step 2: 실패 확인**

Run: `PYTEST tests/test_alerts_api.py -q`
Expected: 첫 테스트 — 정규화 미적용 시 direction 불일치 또는 통과(이미 BOTH 전달이면), basis Literal에 REFERENCE 없으면 422. (Task 1에서 Literal 추가했으므로 생성 자체는 가능; 정규화 보강이 목적.)

- [ ] **Step 3: 구현**

`app/routers/alerts.py`의 `create`(현재 line 13~23)를 교체:

```python
@router.post("", response_model=AlertOut)
async def create(body: AlertCreate, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, body.asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    if body.basis == "PURCHASE_AVG" and not await alert_store.has_holdings(db, body.asset_id):
        raise HTTPException(422, "보유 종목에만 평균매입가 기준 알림을 설정할 수 있습니다.")
    if body.basis in ("WEEK52_HIGH", "WEEK52_LOW") and asset.data_source == "manual":
        raise HTTPException(422, "수동(manual) 자산은 52주 기준 알림을 설정할 수 없습니다.")
    direction = "BOTH" if body.basis == "REFERENCE" else body.direction
    return await alert_store.create_alert(
        db, body.asset_id, body.basis, direction, body.value, body.note)
```

- [ ] **Step 4: 통과 확인**

Run: `PYTEST tests/test_alerts_api.py -q`
Expected: PASS (신규 + 기존 회귀)

- [ ] **Step 5: 전체 백엔드 테스트 + 커밋**

Run: `PYTEST -q`
Expected: 전체 PASS(기존 157 + 신규)

```bash
git add app/routers/alerts.py tests/test_alerts_api.py
git commit -m "feat(alerts): REFERENCE 생성 시 direction=BOTH 정규화"
```

---

### Task 7: 프론트엔드 — 타입·폼·밴드 표시

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/components/AlertForm.tsx`
- Modify: `frontend/src/pages/Alerts.tsx`
- Modify: `frontend/src/pages/AssetDetail.tsx`

- [ ] **Step 1: api.ts 타입 확장**

`frontend/src/api.ts`(line 117~126 부근) 교체:

```typescript
export type AlertBasis = "ABSOLUTE" | "PURCHASE_AVG" | "WEEK52_HIGH" | "WEEK52_LOW" | "REFERENCE";
export type AlertDirection = "ABOVE" | "BELOW" | "BOTH";
export interface AlertCreate {
  asset_id: number; basis: AlertBasis; direction: AlertDirection; value: number; note?: string | null;
}
export interface AlertView {
  alert_id: number; asset_id: number; basis: AlertBasis; direction: AlertDirection;
  value: number; enabled: boolean; is_triggered: boolean; note: string | null;
  target_price: number | null; reference_price: number | null;
  current_price: number | null; price_status: string; fired: boolean;
}
```

- [ ] **Step 2: AlertForm — REFERENCE 옵션 + 방향 숨김**

`frontend/src/components/AlertForm.tsx`:

`BASIS_LABEL`에 항목 추가:

```typescript
export const BASIS_LABEL: Record<AlertBasis, string> = {
  ABSOLUTE: "절대 목표가", PURCHASE_AVG: "평균매입가 대비",
  WEEK52_HIGH: "52주 고점 대비", WEEK52_LOW: "52주 저점 대비",
  REFERENCE: "변동률 감시",
};
```

`unit` 계산을 교체:

```typescript
  const unit = basis === "ABSOLUTE" ? "가격" : basis === "REFERENCE" ? "변동 %" : "%";
```

`add` 함수의 createAlert 호출에서 REFERENCE면 direction을 BOTH로:

```typescript
      await api.createAlert({
        asset_id: cur.asset_id, basis,
        direction: basis === "REFERENCE" ? "BOTH" : dir,
        value: Number(value),
      });
```

방향 select(현재 `<select ...value={dir}...>` 블록)를 REFERENCE일 때 숨김 — 해당 select를 다음으로 감싼다:

```tsx
      {basis !== "REFERENCE" && (
        <select className="input" value={dir} onChange={(e) => setDir(e.target.value as AlertDirection)}>
          <option value="ABOVE">이상 도달</option>
          <option value="BELOW">이하 도달</option>
        </select>
      )}
```

- [ ] **Step 3: Alerts.tsx 허브 테이블 밴드 표시**

`frontend/src/pages/Alerts.tsx`의 방향/목표가 `<td>`(현재 직전 커밋 반영된 line 68~69 부근)를 교체:

```tsx
                <td>{r.basis === "REFERENCE"
                  ? `±${r.value}%`
                  : <>{r.direction === "ABOVE" ? "이상" : "이하"}{r.basis === "ABSOLUTE" ? "" : ` ${r.value}%`}</>}</td>
                <td>{r.basis === "REFERENCE"
                  ? (r.reference_price == null ? "산정 중" : `${r.reference_price.toLocaleString()} ±${r.value}%`)
                  : (r.target_price == null ? "—" : r.target_price.toLocaleString())}</td>
```

상태 `<td>`에서 REFERENCE는 "도달" 배지/발동됨을 쓰지 않고 활성/꺼짐만 — 상태 셀(현재 `r.is_triggered ? ... : r.fired ? ...`)을 교체:

```tsx
                <td>
                  {r.basis !== "REFERENCE" && r.is_triggered
                    ? <span className="text-muted">발동됨</span>
                    : r.basis !== "REFERENCE" && r.fired
                    ? <span className="badge">도달</span>
                    : r.enabled ? <span className="text-up">활성</span>
                    : <span className="text-muted">꺼짐</span>}
                </td>
```

(액션 셀은 그대로 — REFERENCE는 `is_triggered`가 안 되므로 재무장 버튼이 안 뜨고 끄기/켜기·삭제만 노출됨.)

- [ ] **Step 4: AssetDetail.tsx 표시**

`frontend/src/pages/AssetDetail.tsx`의 알림 테이블 행(현재 line 163~166 부근)을 교체:

```tsx
                <td className="py-1">{BASIS_LABEL[al.basis]}</td>
                <td>{al.basis === "REFERENCE" ? `±${al.value}%` : (al.direction === "ABOVE" ? "이상" : "이하")}</td>
                <td>{al.basis === "REFERENCE" ? "—" : <>{al.value}{al.basis === "ABSOLUTE" ? "" : "%"}</>}</td>
                <td>{al.basis === "REFERENCE"
                  ? (al.reference_price == null ? "산정 중" : `${al.reference_price.toLocaleString()} ±${al.value}%`)
                  : (al.target_price == null ? "—" : al.target_price.toLocaleString())}</td>
```

- [ ] **Step 5: 타입체크·빌드**

Run: `cd frontend && npx tsc -b && npm run build`
Expected: tsc 에러 0, 빌드 성공

- [ ] **Step 6: 커밋**

```bash
git add frontend/src/api.ts frontend/src/components/AlertForm.tsx frontend/src/pages/Alerts.tsx frontend/src/pages/AssetDetail.tsx
git commit -m "feat(alerts): REFERENCE 변동률 알림 UI(폼 옵션+방향숨김+기준가±X% 밴드)"
```

---

### Task 8: DB 마이그레이션(dev) + 수동 스모크

**Files:** (코드 변경 없음 — 운영 작업)

- [ ] **Step 1: dev DB에 컬럼 추가(ALTER in-place)**

`ensure_schema`는 create-only라 기존 `invest` 스키마는 수동 ALTER 필요. postgres MCP(`mcp__postgres-agent__execute_sql`) 또는 psql로 실행:

```sql
ALTER TABLE invest.price_alerts ADD COLUMN IF NOT EXISTS reference_price NUMERIC;
```

확인:
```sql
SELECT column_name FROM information_schema.columns
WHERE table_schema='invest' AND table_name='price_alerts' AND column_name='reference_price';
```
Expected: `reference_price` 1행 반환.

- [ ] **Step 2: 앱 기동 후 수동 스모크(사용자 확인)**

백엔드(`.venv/bin/uvicorn app.main:app --port 8000`) + 프론트(vite 또는 빌드된 SPA)에서:
1. 알림 허브 → "변동률 감시" 선택 시 방향 드롭다운 사라짐, value 라벨 "변동 %".
2. 보유/관심 종목에 REFERENCE 알림(예: 5%) 추가 → 목록에 방향 `±5%`, 목표가 `산정 중`(첫 tick 전) 표시.
3. 상태 열 "활성", 액션은 끄기/삭제만(재무장 없음).
4. 대시보드/관심종목 행 알림 개수 배지에 REFERENCE 포함되는지.

(실제 발동/텔레그램은 장중 + ±5% 변동 필요라 즉시 확인 어려움 — 표시·생성 흐름까지만 스모크. 발동 로직은 Task 4 단위테스트로 커버됨.)

- [ ] **Step 3: 최종 커밋(필요 시 스모크 메모/스펙·플랜 상태 갱신)**

스모크에서 수정사항 없으면 추가 커밋 불필요. 로드맵 반영은 머지 후 별도 처리.

---

## 마무리(플랜 외)

- 전 태스크 완료 후 `superpowers:finishing-a-development-branch`로 main 병합(no-ff) 판단.
- 머지 후 `ROADMAP.md`·관련 메모리(`holding-watchlist-ia-and-alerts`)에 REFERENCE 알림 완료 반영.
