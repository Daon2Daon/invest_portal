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

  useEffect(() => {
    setLoading(true);
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
              className={`badge ${p === period ? "btn-primary" : ""}`}>{p}</button>
          ))}
        </div>
      </div>
      {loading ? (
        <p className="text-sm text-muted">불러오는 중…</p>
      ) : data.length < 2 ? (
        <p className="text-sm text-muted">스냅샷이 충분히 쌓이면 추세가 표시됩니다.</p>
      ) : (
        <>
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
            <polyline fill="none" stroke="var(--accent)" strokeWidth={2} points={points} />
            {data.map((d, i) => (
              <circle key={d.date} cx={px(i)} cy={py(d.total_value_krw)} r={2.5} fill="var(--accent)">
                <title>{d.date} · {krw(d.total_value_krw)}</title>
              </circle>
            ))}
          </svg>
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
