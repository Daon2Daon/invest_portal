import io
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.patches import Rectangle


def _setup_font() -> str | None:
    for path in ("/System/Library/Fonts/AppleSDGothicNeo.ttc",
                 "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"):
        if os.path.exists(path):
            try:
                font_manager.fontManager.addfont(path)
                return font_manager.FontProperties(fname=path).get_name()
            except Exception:
                pass
    return None


_FONT_FAMILY: str | None = _setup_font()


def _rc() -> dict:
    rc: dict = {"axes.unicode_minus": False}
    if _FONT_FAMILY:
        rc["font.family"] = _FONT_FAMILY
    return rc


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
    return df.resample("W-FRI").agg(agg).dropna()


def _volume_profile(df: pd.DataFrame, bins: int = 50):
    """가격대별 누적 거래량(매물대)을 계산한다. 각 캔들의 거래량을 그 캔들이 걸치는
    가격 구간들에 균등 분배한다. (price_centers, volume_profile) 반환, 둘 다 길이 bins-1."""
    price_min, price_max = float(df["Low"].min()), float(df["High"].max())
    if price_min >= price_max:
        price_max = price_min + 1
    price_bins = np.linspace(price_min, price_max, bins)
    profile = np.zeros(bins - 1)
    for _, row in df.iterrows():
        lo, hi, vol = float(row["Low"]), float(row["High"]), float(row["Volume"])
        idx = np.where((price_bins[:-1] <= hi) & (price_bins[1:] >= lo))[0]
        if len(idx) > 0:
            per = vol / len(idx)
            for bi in idx:
                if bi < len(profile):
                    profile[bi] += per
    centers = (price_bins[:-1] + price_bins[1:]) / 2
    return centers, profile


def _plot_candles(ax, df, width=0.6):
    for i, (_, row) in enumerate(df.iterrows()):
        o, c, h, l = float(row["Open"]), float(row["Close"]), float(row["High"]), float(row["Low"])
        color = "green" if c >= o else "red"
        ax.plot([i, i], [l, h], color=color, linewidth=0.8)
        body_h = abs(c - o) or 0.001
        ax.add_patch(Rectangle((i - width / 2, min(o, c)), width, body_h,
                               facecolor=color, edgecolor=color, linewidth=0.5))


def generate_ta_chart(df: pd.DataFrame, ticker: str, name: str, timeframe: str) -> bytes:
    """4패널 TA 차트(PNG bytes). df는 OHLCV(DatetimeIndex). 데이터 부족 시 ValueError.

    pyplot 글로벌 상태를 일절 사용하지 않으므로 멀티스레드 동시 호출에 안전하다.
    """
    if df is None or len(df) < 20:
        raise ValueError("차트 생성에 필요한 데이터가 부족합니다(최소 20봉).")
    df = calculate_indicators(df)
    x = np.arange(len(df))

    fig = Figure(figsize=(14, 10))
    FigureCanvasAgg(fig)
    fig.set_facecolor("white")
    with matplotlib.rc_context(_rc()):
        (ax1, ax2, ax3, ax4) = fig.subplots(
            4, 1, gridspec_kw={"height_ratios": [3, 1, 1, 1]})
        fig.suptitle(f"{name} ({ticker}) - {timeframe} - Technical Analysis",
                     fontsize=14, fontweight="bold")
        _plot_candles(ax1, df)
        # 매물대(Volume Profile): 이평선/볼린저 뒤에 깔리도록 캔들 직후, twiny 축에 가로막대로.
        centers, vp = _volume_profile(df)
        vmax = float(vp.max())
        if vmax > 0:
            ax1v = ax1.twiny()
            h = (centers[1] - centers[0]) * 0.95 if len(centers) > 1 else 1
            ax1v.barh(centers, vp, height=h, color="orange", alpha=0.12, zorder=0)
            ax1v.set_xlim(0, vmax)
            ax1v.set_xticks([])
        ax1.plot(x, df["EMA12"].values, color="red", alpha=0.7, linewidth=1.5, label="EMA 12")
        ax1.plot(x, df["EMA26"].values, color="blue", alpha=0.7, linewidth=1.5, label="EMA 26")
        ax1.plot(x, df["SMA20"].values, color="darkgreen", alpha=0.6, linewidth=1.5, label="SMA 20")
        ax1.plot(x, df["SMA50"].values, color="orange", alpha=0.6, linewidth=1.5, label="SMA 50")
        ax1.fill_between(x, df["BB_upper"].values, df["BB_lower"].values, color="gray", alpha=0.15, label="BB")
        ax1.plot(x, df["BB_upper"].values, color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
        ax1.plot(x, df["BB_lower"].values, color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
        ax1.set_ylabel("Price", fontweight="bold"); ax1.legend(loc="upper left", fontsize=8)
        ax1.grid(True, alpha=0.3); ax1.set_xlim(-1, len(df))
        ax2.plot(x, df["RSI"].values, color="purple", linewidth=1.5)
        ax2.axhline(70, color="red", linestyle="--", alpha=0.5)
        ax2.axhline(30, color="green", linestyle="--", alpha=0.5)
        ax2.fill_between(x, 30, 70, color="yellow", alpha=0.1)
        ax2.set_ylabel("RSI(14)", fontweight="bold"); ax2.set_ylim(0, 100)
        ax2.grid(True, alpha=0.3); ax2.set_xlim(-1, len(df))
        colors = ["green" if v >= 0 else "red" for v in df["Histogram"].values]
        ax3.bar(x, df["Histogram"].values, color=colors, alpha=0.3)
        ax3.plot(x, df["MACD"].values, color="blue", linewidth=1.5, label="MACD")
        ax3.plot(x, df["Signal"].values, color="red", linewidth=1.5, label="Signal")
        ax3.axhline(0, color="black", linestyle="-", alpha=0.3)
        ax3.set_ylabel("MACD", fontweight="bold"); ax3.legend(loc="upper left", fontsize=8)
        ax3.grid(True, alpha=0.3); ax3.set_xlim(-1, len(df))
        closes, vols = df["Close"].values, df["Volume"].values
        for i in range(len(closes)):
            col = "green" if (i == 0 or closes[i] >= closes[i - 1]) else "red"
            ax4.bar(i, vols[i], color=col, alpha=0.6)
        ax4.plot(x, df["Volume"].rolling(20).mean().values, color="blue", linewidth=2, label="SMA 20")
        ax4.set_ylabel("Volume", fontweight="bold"); ax4.set_xlabel("Date", fontweight="bold")
        ax4.legend(loc="upper left", fontsize=8); ax4.grid(True, alpha=0.3); ax4.set_xlim(-1, len(df))
        labels = [d.strftime("%Y-%m") for d in df.index]
        step = max(1, len(df) // 12)
        pos = np.arange(0, len(df), step)
        for ax in (ax1, ax2, ax3, ax4):
            ax.set_xticks(pos)
            ax.set_xticklabels([labels[i] if i < len(labels) else "" for i in pos], rotation=45, ha="right")
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    return buf.getvalue()
