# 차트 생성 + 텔레그램 발송 (2a+2b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 보유/지정 자산의 4패널 TA 차트(일봉·주봉)를 생성해 화면에서 조회하고 텔레그램으로 발송한다.

**Architecture:** provider에 OHLCV `history()`를 추가하고(data_source 디스패치), matplotlib(Agg)로 4패널 차트 PNG bytes를 온더플라이 생성한다. `GET /api/charts/{asset_id}`가 PNG를 스트리밍하고, `POST /api/charts/{asset_id}/send-telegram`이 텔레그램 설정(app_settings, 봇토큰 Fernet)을 읽어 사진을 발송한다. 프론트에 "차트"·"설정" 메뉴를 추가한다.

**Tech Stack:** Python(FastAPI, async SQLAlchemy, asyncpg), matplotlib, pandas, numpy, yfinance, pykrx, httpx, pytest / React+Vite+TS+Tailwind.

**참조:** spec `docs/superpowers/specs/2026-06-14-chart-generation-telegram-design.md`. 코드 참고: my-assistant `chart_bot.py`·`telegram_sender.py`(복사 아님, 검증 로직 선별 참조). `.venv/bin/python`·`.venv/bin/pytest`. DB 비밀번호 `mook123!`.

---

## 파일 구조
```
app/services/market/
├── base.py                  # 수정: PriceProvider.history 시그니처
├── yfinance_provider.py     # 수정: history()
├── pykrx_provider.py        # 수정: history()
├── manual_provider.py       # 수정: history()(None)
└── history_service.py       # 신규: get_history 디스패치 + 컬럼 정규화
app/services/chart/chart_service.py        # 신규: 지표 + 4패널 차트 PNG, 주봉 리샘플
app/services/notification/telegram_service.py  # 신규: send_photo/send_message
app/routers/charts.py        # 신규: GET 차트, POST send-telegram
app/routers/settings.py      # 수정: 텔레그램 묶음 get/put
app/main.py                  # 수정: charts 라우터 등록
requirements.txt             # 수정: matplotlib
Dockerfile                   # 수정: fonts-nanum 설치
frontend/src/
├── api.ts                   # 수정: chartUrl, sendChartTelegram, telegram 설정
├── pages/Charts.tsx         # 신규
├── pages/Settings.tsx       # 신규(텔레그램 섹션)
└── App.tsx                  # 수정: /charts, /settings 라우트·네비
```

---

## Task 1: 의존성 (matplotlib) + Dockerfile 한글폰트

**Files:** Modify `requirements.txt`, `Dockerfile`

- [ ] **Step 1: requirements.txt — matplotlib 추가.** `pandas>=2.2.0` 줄 다음에 추가:
```
pandas>=2.2.0
matplotlib>=3.8.0
```

- [ ] **Step 2: venv 설치** → `.venv/bin/pip install matplotlib>=3.8.0` (이미 설치돼 있으면 그대로). 확인: `.venv/bin/python -c "import matplotlib; matplotlib.use('Agg'); print(matplotlib.__version__)"`.

- [ ] **Step 3: Dockerfile — python 런타임 단계에 한글폰트 설치.** `WORKDIR /app` 다음, `COPY requirements.txt .` 앞에 추가:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends fonts-nanum \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 4: Commit**
```bash
git add requirements.txt Dockerfile
git commit -m "build: add matplotlib + nanum font for charts"
```

---

## Task 2: provider history() + 프로토콜

**Files:** Modify `app/services/market/base.py`, `yfinance_provider.py`, `pykrx_provider.py`, `manual_provider.py`; Create `tests/test_provider_history.py`

- [ ] **Step 1: tests/test_provider_history.py 작성**
```python
from unittest.mock import patch, MagicMock
import pandas as pd
from app.services.market.yfinance_provider import YFinanceProvider
from app.services.market.pykrx_provider import PykrxProvider
from app.services.market.manual_provider import ManualProvider


@patch("app.services.market.yfinance_provider.yf.Ticker")
def test_yfinance_history_returns_ohlcv(mock_ticker):
    inst = MagicMock()
    inst.history.return_value = pd.DataFrame({
        "Open": [1.0, 2.0], "High": [2, 3], "Low": [0.5, 1], "Close": [1.5, 2.5],
        "Volume": [10, 20], "Dividends": [0, 0]})
    mock_ticker.return_value = inst
    df = YFinanceProvider().history("AAPL", "US", 365)
    assert df is not None and len(df) == 2
    assert {"Open", "High", "Low", "Close", "Volume"} <= set(df.columns)


@patch("app.services.market.pykrx_provider.stock")
def test_pykrx_history_renames_korean_cols(mock_stock):
    mock_stock.get_market_ohlcv_by_date.return_value = pd.DataFrame({
        "시가": [70000], "고가": [71000], "저가": [69000], "종가": [70500], "거래량": [100]})
    df = PykrxProvider().history("005930", "KR", 365)
    assert df is not None
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df["Close"].iloc[-1] == 70500


def test_manual_history_is_none():
    assert ManualProvider().history("X", "KR", 365) is None
```

- [ ] **Step 2: Run `.venv/bin/pytest tests/test_provider_history.py -q`** → FAIL (no history()).

- [ ] **Step 3: app/services/market/base.py — 프로토콜에 history 추가** (quote 다음):
```python
    def quote(self, fetch_symbol: str, currency: str, asset_type: str) -> Quote | None:
        ...

    def history(self, fetch_symbol: str, market: str, days: int):
        ...
```

- [ ] **Step 4: yfinance_provider.py — history 추가.** 파일 상단 import에 `from datetime import date, timedelta`가 있는지 확인(없으면 `date`만 있을 수 있음 → `timedelta` 추가). 클래스에 메서드 추가(quote 다음):
```python
    def history(self, fetch_symbol, market, days):
        try:
            start = (date.today() - timedelta(days=days)).isoformat()
            df = yf.Ticker(fetch_symbol).history(start=start, auto_adjust=False)
            if df is None or df.empty:
                return None
            cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            if len(cols) < 5:
                return None
            return df[["Open", "High", "Low", "Close", "Volume"]].copy()
        except Exception:
            return None
```
(파일 맨 위 `from datetime import date`를 `from datetime import date, timedelta`로 바꾼다.)

- [ ] **Step 5: pykrx_provider.py — history 추가.** 상단에 이미 `from datetime import datetime, timedelta, date`, `from zoneinfo import ZoneInfo`, `from pykrx import stock` 있음. 클래스에 추가(quote 다음):
```python
    def history(self, fetch_symbol, market, days):
        try:
            today = datetime.now(ZoneInfo("Asia/Seoul"))
            end = today.strftime("%Y%m%d")
            start = (today - timedelta(days=days)).strftime("%Y%m%d")
            df = stock.get_market_ohlcv_by_date(start, end, fetch_symbol)
            if df is None or df.empty:
                return None
            df = df.rename(columns={"시가": "Open", "고가": "High", "저가": "Low",
                                    "종가": "Close", "거래량": "Volume"})
            need = ["Open", "High", "Low", "Close", "Volume"]
            if not all(c in df.columns for c in need):
                return None
            return df[need].copy()
        except Exception:
            return None
```

- [ ] **Step 6: manual_provider.py — history 추가**(quote 다음):
```python
    def history(self, fetch_symbol, market, days):
        return None  # 수동 자산은 시세 이력이 없어 차트 불가
```

- [ ] **Step 7: Run `.venv/bin/pytest tests/test_provider_history.py -q`** → 3 PASS. 전체 `.venv/bin/pytest -q` 회귀 확인.

- [ ] **Step 8: Commit**
```bash
git add app/services/market/base.py app/services/market/yfinance_provider.py app/services/market/pykrx_provider.py app/services/market/manual_provider.py tests/test_provider_history.py
git commit -m "feat: provider.history() for OHLCV (yfinance/pykrx; manual none)"
```

---

## Task 3: history_service (디스패치 + 정규화)

**Files:** Create `app/services/market/history_service.py`, `tests/test_history_service.py`

- [ ] **Step 1: tests/test_history_service.py**
```python
import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import pandas as pd
from app.services.market.history_service import get_history


@pytest.mark.asyncio
async def test_get_history_dispatches_by_data_source():
    asset = SimpleNamespace(data_source="yfinance", fetch_symbol="AAPL", market="US")
    fake = pd.DataFrame({"Open":[1],"High":[1],"Low":[1],"Close":[1],"Volume":[1]})
    with patch("app.services.market.history_service.registry") as reg:
        reg.for_source.return_value = MagicMock(history=MagicMock(return_value=fake))
        df = await get_history(asset, 365)
        reg.for_source.assert_called_once_with("yfinance")
        assert df is not None and len(df) == 1


@pytest.mark.asyncio
async def test_get_history_none_passthrough():
    asset = SimpleNamespace(data_source="manual", fetch_symbol="X", market="KR")
    with patch("app.services.market.history_service.registry") as reg:
        reg.for_source.return_value = MagicMock(history=MagicMock(return_value=None))
        assert await get_history(asset, 365) is None
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: app/services/market/history_service.py**
```python
import asyncio
from app.services.market.registry import registry


async def get_history(asset, days: int):
    """자산의 data_source에 맞는 provider로 일봉 OHLCV(DataFrame)를 조회한다(블로킹 → 스레드).
    컬럼은 provider가 Open/High/Low/Close/Volume 으로 정규화해 반환한다. 없으면 None."""
    provider = registry.for_source(asset.data_source)
    return await asyncio.to_thread(provider.history, asset.fetch_symbol, asset.market, days)
```

- [ ] **Step 4: Run `.venv/bin/pytest tests/test_history_service.py -q`** → 2 PASS.

- [ ] **Step 5: Commit**
```bash
git add app/services/market/history_service.py tests/test_history_service.py
git commit -m "feat: history_service dispatching OHLCV by data_source"
```

---

## Task 4: chart_service (지표 + 4패널 차트 + 주봉 리샘플)

**Files:** Create `app/services/chart/__init__.py`, `app/services/chart/chart_service.py`, `tests/test_chart_service.py`

- [ ] **Step 1: tests/test_chart_service.py**
```python
import numpy as np
import pandas as pd
from app.services.chart.chart_service import calculate_indicators, to_weekly, generate_ta_chart


def _ohlcv(n=80):
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    base = np.linspace(100, 120, n)
    return pd.DataFrame({
        "Open": base, "High": base + 2, "Low": base - 2, "Close": base + 1,
        "Volume": np.arange(1, n + 1) * 1000.0}, index=idx)


def test_calculate_indicators_adds_columns_and_rsi_range():
    df = calculate_indicators(_ohlcv())
    for col in ["EMA12", "EMA26", "SMA20", "BB_upper", "BB_lower", "RSI", "MACD", "Signal", "Histogram"]:
        assert col in df.columns
    rsi = df["RSI"].dropna()
    assert (rsi >= 0).all() and (rsi <= 100).all()
    # MACD = EMA12 - EMA26
    assert np.allclose((df["EMA12"] - df["EMA26"]).values, df["MACD"].values, equal_nan=True)


def test_to_weekly_aggregates():
    df = _ohlcv(14)  # 2주
    w = to_weekly(df)
    assert len(w) <= 3
    assert {"Open", "High", "Low", "Close", "Volume"} <= set(w.columns)
    # 주 마지막 종가 = 해당 주 마지막 일봉 종가
    assert w["High"].iloc[0] >= df["High"].iloc[0]


def test_generate_ta_chart_returns_png_bytes():
    png = generate_ta_chart(_ohlcv(), ticker="TEST", name="테스트종목", timeframe="DAILY")
    assert isinstance(png, (bytes, bytearray))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"   # PNG 매직넘버
    assert len(png) > 1000
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: app/services/chart/__init__.py (빈 파일) + app/services/chart/chart_service.py**
```python
import io
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle


def _setup_font():
    for path in ("/System/Library/Fonts/AppleSDGothicNeo.ttc",
                 "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"):
        if os.path.exists(path):
            try:
                font_manager.fontManager.addfont(path)
                plt.rcParams["font.family"] = font_manager.FontProperties(fname=path).get_name()
                break
            except Exception:
                pass
    plt.rcParams["axes.unicode_minus"] = False


_setup_font()


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["EMA12"] = df["Close"].ewm(span=12, adjust=False).mean()
    df["EMA26"] = df["Close"].ewm(span=26, adjust=False).mean()
    df["SMA20"] = df["Close"].rolling(20).mean()
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["BB20"] = df["Close"].rolling(20).mean()
    df["BB_std"] = df["Close"].rolling(20).std()
    df["BB_upper"] = df["BB20"] + df["BB_std"] * 2
    df["BB_lower"] = df["BB20"] - df["BB_std"] * 2
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean().replace(0, np.nan)
    rs = gain / loss
    df["RSI"] = (100 - 100 / (1 + rs)).fillna(50)
    df["MACD"] = df["EMA12"] - df["EMA26"]
    df["Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["Histogram"] = (df["MACD"] - df["Signal"]).fillna(0)
    return df


def to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    w = df.resample("W-FRI").agg(agg).dropna()
    return w


def _plot_candles(ax, df, width=0.6):
    for i, (_, row) in enumerate(df.iterrows()):
        o, c, h, l = float(row["Open"]), float(row["Close"]), float(row["High"]), float(row["Low"])
        color = "green" if c >= o else "red"
        ax.plot([i, i], [l, h], color=color, linewidth=0.8)
        body_h = abs(c - o) or 0.001
        ax.add_patch(Rectangle((i - width / 2, min(o, c)), width, body_h,
                               facecolor=color, edgecolor=color, linewidth=0.5))


def generate_ta_chart(df: pd.DataFrame, ticker: str, name: str, timeframe: str) -> bytes:
    """4패널 TA 차트(PNG bytes). df는 OHLCV(DatetimeIndex). 데이터 부족 시 ValueError."""
    if df is None or len(df) < 20:
        raise ValueError("차트 생성에 필요한 데이터가 부족합니다(최소 20봉).")
    df = calculate_indicators(df)
    x = np.arange(len(df))
    fig, (ax1, ax2, ax3, ax4) = plt.subplots(
        4, 1, figsize=(14, 10), gridspec_kw={"height_ratios": [3, 1, 1, 1]})
    fig.suptitle(f"{name} ({ticker}) - {timeframe} - Technical Analysis",
                 fontsize=14, fontweight="bold")
    # Panel 1
    _plot_candles(ax1, df)
    ax1.plot(x, df["EMA12"].values, color="red", alpha=0.7, linewidth=1.5, label="EMA 12")
    ax1.plot(x, df["EMA26"].values, color="blue", alpha=0.7, linewidth=1.5, label="EMA 26")
    ax1.plot(x, df["SMA20"].values, color="darkgreen", alpha=0.6, linewidth=1.5, label="SMA 20")
    ax1.plot(x, df["SMA50"].values, color="orange", alpha=0.6, linewidth=1.5, label="SMA 50")
    ax1.fill_between(x, df["BB_upper"].values, df["BB_lower"].values, color="gray", alpha=0.15, label="BB")
    ax1.plot(x, df["BB_upper"].values, color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
    ax1.plot(x, df["BB_lower"].values, color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
    ax1.set_ylabel("Price", fontweight="bold"); ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.3); ax1.set_xlim(-1, len(df))
    # Panel 2 RSI
    ax2.plot(x, df["RSI"].values, color="purple", linewidth=1.5)
    ax2.axhline(70, color="red", linestyle="--", alpha=0.5)
    ax2.axhline(30, color="green", linestyle="--", alpha=0.5)
    ax2.fill_between(x, 30, 70, color="yellow", alpha=0.1)
    ax2.set_ylabel("RSI(14)", fontweight="bold"); ax2.set_ylim(0, 100)
    ax2.grid(True, alpha=0.3); ax2.set_xlim(-1, len(df))
    # Panel 3 MACD
    colors = ["green" if v >= 0 else "red" for v in df["Histogram"].values]
    ax3.bar(x, df["Histogram"].values, color=colors, alpha=0.3)
    ax3.plot(x, df["MACD"].values, color="blue", linewidth=1.5, label="MACD")
    ax3.plot(x, df["Signal"].values, color="red", linewidth=1.5, label="Signal")
    ax3.axhline(0, color="black", linestyle="-", alpha=0.3)
    ax3.set_ylabel("MACD", fontweight="bold"); ax3.legend(loc="upper left", fontsize=8)
    ax3.grid(True, alpha=0.3); ax3.set_xlim(-1, len(df))
    # Panel 4 Volume
    closes, vols = df["Close"].values, df["Volume"].values
    for i in range(len(closes)):
        col = "green" if (i == 0 or closes[i] >= closes[i - 1]) else "red"
        ax4.bar(i, vols[i], color=col, alpha=0.6)
    ax4.plot(x, df["Volume"].rolling(20).mean().values, color="blue", linewidth=2, label="SMA 20")
    ax4.set_ylabel("Volume", fontweight="bold"); ax4.set_xlabel("Date", fontweight="bold")
    ax4.legend(loc="upper left", fontsize=8); ax4.grid(True, alpha=0.3); ax4.set_xlim(-1, len(df))
    # x labels
    labels = [d.strftime("%Y-%m") for d in df.index]
    step = max(1, len(df) // 12)
    pos = np.arange(0, len(df), step)
    for ax in (ax1, ax2, ax3, ax4):
        ax.set_xticks(pos)
        ax.set_xticklabels([labels[i] if i < len(labels) else "" for i in pos], rotation=45, ha="right")
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()
```

- [ ] **Step 4: Run `.venv/bin/pytest tests/test_chart_service.py -q`** → 3 PASS.

- [ ] **Step 5: Commit**
```bash
git add app/services/chart/ tests/test_chart_service.py
git commit -m "feat: chart_service (TA indicators, 4-panel PNG, weekly resample)"
```

---

## Task 5: charts 라우터 (GET 차트) + main 등록

**Files:** Create `app/routers/charts.py`; Modify `app/main.py`

- [ ] **Step 1: app/routers/charts.py**
```python
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
import io

from app.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Asset
from app.services.market.history_service import get_history
from app.services.chart.chart_service import generate_ta_chart, to_weekly

router = APIRouter(prefix="/api/charts", tags=["charts"])

# period별 일봉 조회 일수
_DAYS = {"daily": 730, "weekly": 1825}


async def _build_png(db: AsyncSession, asset_id: int, period: str) -> bytes:
    if period not in _DAYS:
        raise HTTPException(422, "period는 daily 또는 weekly")
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    df = await get_history(asset, _DAYS[period])
    if df is None or len(df) < 20:
        raise HTTPException(422, "차트용 시세 이력을 가져올 수 없습니다(수동/이력없음 자산이거나 데이터 부족).")
    if period == "weekly":
        df = to_weekly(df)
        if len(df) < 20:
            raise HTTPException(422, "주봉 데이터가 부족합니다.")
    label = "WEEKLY" if period == "weekly" else "DAILY"
    import asyncio
    return await asyncio.to_thread(generate_ta_chart, df, asset.ticker, asset.name, label)


@router.get("/{asset_id}")
async def chart(asset_id: int, period: str = Query("daily"), db: AsyncSession = Depends(get_db)):
    png = await _build_png(db, asset_id, period)
    return StreamingResponse(io.BytesIO(png), media_type="image/png")
```

- [ ] **Step 2: app/main.py — charts 라우터 등록.** import 줄에 `charts` 추가, 등록 루프 튜플에 `charts.router` 추가:
```python
from app.routers import assets, holdings, portfolio, fx, settings as settings_router, cash, charts
```
```python
for r in (assets.router, holdings.router, portfolio.router, fx.router, settings_router.router, cash.router, charts.router):
    app.include_router(r)
```

- [ ] **Step 3: Verify**
```bash
.venv/bin/python -c "from app.main import app; ps={r.path for r in app.routes}; print('/api/charts/{asset_id}' in ps)"  # True
.venv/bin/pytest -q 2>&1 | tail -1
```

- [ ] **Step 4: Commit**
```bash
git add app/routers/charts.py app/main.py
git commit -m "feat: charts router (GET PNG) + register"
```

---

## Task 6: telegram_service

**Files:** Create `app/services/notification/__init__.py`, `app/services/notification/telegram_service.py`, `tests/test_telegram_service.py`

- [ ] **Step 1: tests/test_telegram_service.py**
```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.notification import telegram_service as ts


@pytest.mark.asyncio
async def test_send_photo_missing_token_raises():
    db = MagicMock()
    with patch.object(ts, "_load_config", AsyncMock(return_value=(None, None))):
        with pytest.raises(ts.TelegramNotConfigured):
            await ts.send_photo(db, b"\x89PNG", "cap")


@pytest.mark.asyncio
async def test_send_photo_posts_to_telegram():
    db = MagicMock()
    resp = MagicMock(status_code=200)
    client = AsyncMock(); client.post = AsyncMock(return_value=resp)
    cm = MagicMock(); cm.__aenter__ = AsyncMock(return_value=client); cm.__aexit__ = AsyncMock(return_value=False)
    with patch.object(ts, "_load_config", AsyncMock(return_value=("TOKEN", "CHAT"))), \
         patch("app.services.notification.telegram_service.httpx.AsyncClient", return_value=cm):
        ok = await ts.send_photo(db, b"\x89PNG", "cap")
        assert ok is True
        args, kwargs = client.post.call_args
        assert "/botTOKEN/sendPhoto" in args[0]
        assert kwargs["data"]["chat_id"] == "CHAT"
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: app/services/notification/__init__.py (빈 파일) + telegram_service.py**
```python
import asyncio
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.settings.settings_manager import get_setting

CATEGORY = "notification"


class TelegramNotConfigured(Exception):
    pass


async def _load_config(db: AsyncSession):
    token = await get_setting(db, CATEGORY, "telegram_bot_token")
    chat_id = await get_setting(db, CATEGORY, "telegram_chat_id")
    return token, chat_id


async def send_photo(db: AsyncSession, png: bytes, caption: str = "") -> bool:
    token, chat_id = await _load_config(db)
    if not token or not chat_id:
        raise TelegramNotConfigured("텔레그램 봇 토큰/chat_id가 설정되지 않았습니다.")
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    files = {"photo": ("chart.png", png, "image/png")}
    data = {"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "HTML"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, data=data, files=files)
    return resp.status_code == 200


async def send_message(db: AsyncSession, text: str) -> bool:
    token, chat_id = await _load_config(db)
    if not token or not chat_id:
        raise TelegramNotConfigured("텔레그램 봇 토큰/chat_id가 설정되지 않았습니다.")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    timeout = httpx.Timeout(60.0, connect=15.0)
    for attempt, backoff in enumerate((1.0, 3.0, 8.0, None)):
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=data)
        if resp.status_code == 200:
            return True
        if resp.status_code in (429,) or resp.status_code >= 500:
            if backoff is None:
                return False
            await asyncio.sleep(backoff)
            continue
        return False
    return False
```

- [ ] **Step 4: Run `.venv/bin/pytest tests/test_telegram_service.py -q`** → 2 PASS.

- [ ] **Step 5: Commit**
```bash
git add app/services/notification/ tests/test_telegram_service.py
git commit -m "feat: telegram_service (send_photo/send_message, settings-backed)"
```

---

## Task 7: charts send-telegram 엔드포인트

**Files:** Modify `app/routers/charts.py`

- [ ] **Step 1: app/routers/charts.py — import + 발송 엔드포인트 추가.**
상단 import에 추가:
```python
from app.services.notification import telegram_service
from app.services.market.quote_service import get_quote
```
파일 끝에 라우트 추가:
```python
@router.post("/{asset_id}/send-telegram")
async def send_telegram(asset_id: int, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    quote = await get_quote(asset)
    caption = f"<b>{asset.name}</b> ({asset.ticker}·{asset.market})\n현재가: {quote.price:,} {asset.currency}"
    sent = 0
    try:
        for period in ("daily", "weekly"):
            png = await _build_png(db, asset_id, period)
            cap = f"{caption}\n[{period.upper()}]"
            if await telegram_service.send_photo(db, png, cap):
                sent += 1
    except telegram_service.TelegramNotConfigured as e:
        raise HTTPException(409, str(e))
    return {"sent": sent, "ok": sent > 0}
```

- [ ] **Step 2: Verify route** → `.venv/bin/python -c "from app.routers.charts import router; print(any(r.path=='/api/charts/{asset_id}/send-telegram' for r in router.routes))"` → True. 전체 `.venv/bin/pytest -q` 회귀.

- [ ] **Step 3: Commit**
```bash
git add app/routers/charts.py
git commit -m "feat: POST /api/charts/{id}/send-telegram (daily+weekly photos)"
```

---

## Task 8: settings 라우터 — 텔레그램 묶음 get/put

**Files:** Modify `app/routers/settings.py`

- [ ] **Step 1: app/routers/settings.py 전체 교체**
```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.services.settings.settings_manager import get_setting, set_setting

router = APIRouter(prefix="/api/settings", tags=["settings"])

_CAT = "notification"


class SettingIn(BaseModel):
    category: str
    key: str
    value: str
    is_secret: bool = False


class TelegramIn(BaseModel):
    bot_token: str | None = None   # 빈/None이면 기존 토큰 유지
    chat_id: str | None = None


@router.get("/telegram")
async def get_telegram(db: AsyncSession = Depends(get_db)):
    token = await get_setting(db, _CAT, "telegram_bot_token")
    chat_id = await get_setting(db, _CAT, "telegram_chat_id")
    return {"bot_token_set": bool(token), "chat_id": chat_id or ""}


@router.put("/telegram")
async def put_telegram(body: TelegramIn, db: AsyncSession = Depends(get_db)):
    if body.bot_token:
        await set_setting(db, _CAT, "telegram_bot_token", body.bot_token, is_secret=True)
    if body.chat_id is not None:
        await set_setting(db, _CAT, "telegram_chat_id", body.chat_id, is_secret=False)
    return {"status": "ok"}


@router.get("/{category}/{key}")
async def read(category: str, key: str, db: AsyncSession = Depends(get_db)):
    return {"value": await get_setting(db, category, key)}


@router.put("")
async def write(body: SettingIn, db: AsyncSession = Depends(get_db)):
    await set_setting(db, body.category, body.key, body.value, body.is_secret)
    return {"status": "ok"}
```

- [ ] **Step 2: Verify** → `.venv/bin/python -c "from app.main import app; ps={(r.path) for r in app.routes}; print('/api/settings/telegram' in ps)"` → True.

- [ ] **Step 3: Commit**
```bash
git add app/routers/settings.py
git commit -m "feat: telegram settings bundle endpoints (masked token)"
```

---

## Task 9: 프론트 api.ts

**Files:** Modify `frontend/src/api.ts`

- [ ] **Step 1: api 객체에 추가** (`deleteCash` 다음 줄):
```ts
  chartUrl: (id: number, period: "daily" | "weekly") => `/api/charts/${id}?period=${period}`,
  sendChartTelegram: (id: number) => j(`/api/charts/${id}/send-telegram`, { method: "POST" }),
  getTelegram: () => j<{ bot_token_set: boolean; chat_id: string }>("/api/settings/telegram"),
  saveTelegram: (t: { bot_token?: string; chat_id?: string }) =>
    j("/api/settings/telegram", { method: "PUT", body: JSON.stringify(t) }),
```

- [ ] **Step 2: Build** → `cd frontend && npm run build 2>&1 | tail -2` 성공.

- [ ] **Step 3: Commit**
```bash
git add frontend/src/api.ts
git commit -m "feat(frontend): chart + telegram api methods"
```

---

## Task 10: 프론트 Charts.tsx

**Files:** Create `frontend/src/pages/Charts.tsx`

- [ ] **Step 1: frontend/src/pages/Charts.tsx**
```tsx
import { useEffect, useState } from "react";
import { api } from "../api";

export default function Charts() {
  const [assets, setAssets] = useState<any[]>([]);
  const [assetId, setAssetId] = useState<number | null>(null);
  const [nonce, setNonce] = useState(0);     // 이미지 캐시 버스트
  const [msg, setMsg] = useState("");

  useEffect(() => { api.listAssets().then((a) => { setAssets(a); if (a[0]) setAssetId(a[0].asset_id); }); }, []);

  const send = async () => {
    if (!assetId) return;
    setMsg("발송 중…");
    try {
      const r: any = await api.sendChartTelegram(assetId);
      setMsg(r.ok ? `텔레그램 발송 완료 (${r.sent}장)` : "발송 실패");
    } catch (e: any) { setMsg("발송 실패: " + e.message); }
  };

  const src = (period: "daily" | "weekly") =>
    assetId ? `${api.chartUrl(assetId, period)}&n=${nonce}` : "";

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <h1 className="text-xl font-bold">차트</h1>
        <select className="border rounded px-2 py-1" value={assetId ?? ""}
          onChange={(e) => { setAssetId(Number(e.target.value)); setMsg(""); }}>
          {assets.map((a) => <option key={a.asset_id} value={a.asset_id}>{a.name} ({a.ticker}·{a.market})</option>)}
        </select>
        <button onClick={() => setNonce((n) => n + 1)} className="px-3 py-1 rounded bg-gray-800 text-white">새로고침</button>
        <button onClick={send} className="px-3 py-1 rounded bg-blue-600 text-white">텔레그램 발송</button>
        {msg && <span className="text-sm text-gray-600">{msg}</span>}
      </div>
      {assetId && (
        <div className="space-y-6">
          <div>
            <h2 className="font-semibold mb-1">일봉</h2>
            <img src={src("daily")} alt="daily chart" className="max-w-full border rounded"
              onError={(e) => ((e.target as HTMLImageElement).alt = "차트를 가져올 수 없습니다(수동/이력없음 자산일 수 있음)")} />
          </div>
          <div>
            <h2 className="font-semibold mb-1">주봉</h2>
            <img src={src("weekly")} alt="weekly chart" className="max-w-full border rounded" />
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Build** (App에 연결 후 Task 11에서 확인). Commit:
```bash
git add frontend/src/pages/Charts.tsx
git commit -m "feat(frontend): Charts page (daily/weekly + telegram send)"
```

---

## Task 11: 프론트 Settings.tsx + 라우팅/네비

**Files:** Create `frontend/src/pages/Settings.tsx`; Modify `frontend/src/App.tsx`

- [ ] **Step 1: frontend/src/pages/Settings.tsx**
```tsx
import { useEffect, useState } from "react";
import { api } from "../api";

export default function Settings() {
  const [chatId, setChatId] = useState("");
  const [token, setToken] = useState("");
  const [tokenSet, setTokenSet] = useState(false);
  const [msg, setMsg] = useState("");

  const load = async () => {
    const t = await api.getTelegram();
    setChatId(t.chat_id); setTokenSet(t.bot_token_set); setToken("");
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    setMsg("저장 중…");
    const payload: any = { chat_id: chatId };
    if (token) payload.bot_token = token;
    await api.saveTelegram(payload);
    setMsg("저장됨"); await load();
  };

  return (
    <div className="p-6 space-y-4 max-w-xl">
      <h1 className="text-xl font-bold">설정</h1>
      <section className="space-y-2">
        <h2 className="font-semibold text-gray-700">텔레그램</h2>
        <div className="flex gap-2 items-center">
          <label className="w-28 text-sm">봇 토큰</label>
          <input className="border rounded px-2 py-1 flex-1" type="password"
            placeholder={tokenSet ? "설정됨 (변경 시에만 입력)" : "봇 토큰 입력"}
            value={token} onChange={(e) => setToken(e.target.value)} />
        </div>
        <div className="flex gap-2 items-center">
          <label className="w-28 text-sm">chat_id</label>
          <input className="border rounded px-2 py-1 flex-1" placeholder="chat_id"
            value={chatId} onChange={(e) => setChatId(e.target.value)} />
        </div>
        <button onClick={save} className="px-3 py-1 rounded bg-blue-600 text-white">저장</button>
        {msg && <span className="text-sm text-gray-600 ml-2">{msg}</span>}
      </section>
    </div>
  );
}
```

- [ ] **Step 2: frontend/src/App.tsx 전체 교체**
```tsx
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Holdings from "./pages/Holdings";
import Charts from "./pages/Charts";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <BrowserRouter>
      <nav className="flex gap-4 border-b px-6 py-3">
        <Link to="/" className="font-semibold">대시보드</Link>
        <Link to="/holdings">보유</Link>
        <Link to="/charts">차트</Link>
        <Link to="/settings">설정</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/holdings" element={<Holdings />} />
        <Route path="/charts" element={<Charts />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </BrowserRouter>
  );
}
```

- [ ] **Step 3: Build** → `cd frontend && npm run build 2>&1 | tail -2` 성공.

- [ ] **Step 4: Commit**
```bash
git add frontend/src/pages/Settings.tsx frontend/src/App.tsx
git commit -m "feat(frontend): Settings page (telegram) + charts/settings routes"
```

---

## Task 12: 최종 검증

**Files:** 없음

- [ ] **Step 1: 백엔드 단위 스위트** → `.venv/bin/pytest -q` → 모든 PASS(+DB skip).
- [ ] **Step 2: 앱 import + 라우트** → `.venv/bin/python -c "from app.main import app; print(len(app.routes),'routes')"` 정상(charts GET·send-telegram, settings/telegram 추가).
- [ ] **Step 3: 프론트 빌드** → `cd frontend && npm run build 2>&1 | tail -2` 성공.
- [ ] **Step 4: (DB/네트워크 가능 시) 실DB 스모크.** 앱 부팅 후: 보유 자산(예: 005930) `GET /api/charts/{id}?period=daily` → 200 `image/png`(PNG 매직바이트). 텔레그램은 설정된 경우만 `POST .../send-telegram` 확인, 아니면 409 확인. 매뉴얼 자산은 422 확인.
- [ ] **Step 5:** (커밋 없음)

---

## Self-Review (spec 대비)
- spec §3 history(provider+service) → Task 2·3. ✅
- spec §4 차트 생성(지표·4패널·주봉·PNG bytes) → Task 4. ✅
- spec §5 차트 API/UI + 메뉴 → Task 5·10·11. ✅
- spec §6 텔레그램(설정·서비스·발송) → Task 6·7·8 + 프론트 Task 9·11. ✅
- spec §2 한글폰트/matplotlib → Task 1. ✅
- spec §8 테스트 → Task 2·3·4·6 단위 + Task 12 스모크. ✅
- spec §9 오류(이력없음 422, 토큰미설정 409, manual 차트불가) → Task 5(_build_png 422)·7(409). ✅

타입/시그니처 일관성: `history(fetch_symbol, market, days)`가 base 프로토콜·3 provider·history_service 호출에서 동일. `generate_ta_chart(df, ticker, name, timeframe)`·`to_weekly(df)`·`calculate_indicators(df)`가 chart_service·charts 라우터·테스트에서 동일. 텔레그램 키(`telegram_bot_token`/`telegram_chat_id`, category `notification`)가 telegram_service·settings 라우터에서 동일. 프론트 `chartUrl`/`sendChartTelegram`/`getTelegram`/`saveTelegram`가 api.ts·Charts·Settings에서 동일.
