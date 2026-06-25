import { useEffect, useState } from "react";
import { api } from "../api";
import type { TrendPoint } from "../api";

const PERIODS = ["1M", "3M", "6M", "1Y", "ALL"] as const;
type Period = (typeof PERIODS)[number];

const krw = (v: number) => "₩" + Math.round(v).toLocaleString("ko-KR");

export default function TrendChart() {
  const [period, setPeriod] = useState<Period>("1M");
  const [data, setData] = useState<TrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    setLoading(true);
    setHover(null);
    api.getTrend(period)
      .then(setData)
      .catch(() => setData([]))
      .finally(() => setLoading(false));
  }, [period]);

  const W = 600, H = 180, PAD = 10;
  const values = data.map((d) => d.total_value_krw);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 1;
  const span = max - min || 1;
  const n = data.length;
  const px = (i: number) => (n <= 1 ? W / 2 : PAD + (i * (W - 2 * PAD)) / (n - 1));
  const py = (v: number) => H - PAD - ((v - min) / span) * (H - 2 * PAD);
  const points = data.map((d, i) => `${px(i)},${py(d.total_value_krw)}`).join(" ");

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <h2 className="font-semibold">자산 추세</h2>
        <div className="flex gap-1">
          {PERIODS.map((p) => (
            <button key={p} onClick={() => setPeriod(p)}
              aria-pressed={p === period}
              className={`btn text-xs px-2 py-1 ${p === period ? "btn-primary" : "btn-ghost"}`}>{p}</button>
          ))}
        </div>
      </div>
      {loading ? (
        <p className="text-sm text-muted">불러오는 중…</p>
      ) : data.length < 2 ? (
        <p className="text-sm text-muted">스냅샷이 충분히 쌓이면 추세가 표시됩니다.</p>
      ) : (
        <>
          <div className="relative" onMouseLeave={() => setHover(null)}>
            <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
              {hover != null && data[hover] && (
                <line x1={px(hover)} y1={0} x2={px(hover)} y2={H}
                  stroke="var(--border)" strokeWidth={1} strokeDasharray="3 3" />
              )}
              <polyline fill="none" stroke="var(--accent)" strokeWidth={2} points={points} />
              {data.map((d, i) => (
                <circle key={d.date} cx={px(i)} cy={py(d.total_value_krw)}
                  r={i === hover ? 4 : 2.5} fill="var(--accent)" />
              ))}
              {/* 호버 히트 영역(넓게) — 점 정확히 안 맞춰도 잡히도록 */}
              {data.map((d, i) => (
                <circle key={`hit-${d.date}`} cx={px(i)} cy={py(d.total_value_krw)} r={12}
                  fill="transparent" style={{ cursor: "pointer" }}
                  onMouseEnter={() => setHover(i)} onClick={() => setHover(i)}>
                  <title>{d.date} · {krw(d.total_value_krw)}</title>
                </circle>
              ))}
            </svg>
            {hover != null && data[hover] && (
              <div className={`absolute z-10 pointer-events-none -translate-x-1/2 whitespace-nowrap rounded px-2 py-1 text-xs shadow ${
                py(data[hover].total_value_krw) / H < 0.35 ? "translate-y-2" : "-translate-y-full -mt-2"
              }`}
                style={{
                  left: `${(px(hover) / W) * 100}%`,
                  top: `${(py(data[hover].total_value_krw) / H) * 100}%`,
                  background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)",
                }}>
                <div className="text-muted">{data[hover].date}</div>
                <div className="font-semibold">{krw(data[hover].total_value_krw)}</div>
              </div>
            )}
          </div>
          <div className="flex justify-between text-xs text-muted mt-1">
            <span>{data[0].date}</span>
            <span>최신 {krw(data[data.length - 1].total_value_krw)}</span>
            <span>{data[data.length - 1].date}</span>
          </div>
        </>
      )}
    </div>
  );
}
