import { useEffect, useState } from "react";
import { api } from "../api";
import type { PortfolioOut } from "../api";

const krw = (n: number) => n.toLocaleString("ko-KR", { maximumFractionDigits: 0 });

export default function Dashboard() {
  const [data, setData] = useState<PortfolioOut | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => setData(await api.portfolio());
  const refresh = async () => { setLoading(true); try { setData(await api.refresh()); } finally { setLoading(false); } };
  useEffect(() => { load(); }, []);

  if (!data) return <div className="p-6">불러오는 중…</div>;
  const s = data.summary;
  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">포트폴리오</h1>
        <button onClick={refresh} disabled={loading}
          className="px-3 py-1.5 rounded bg-blue-600 text-white disabled:opacity-50">
          {loading ? "갱신 중…" : "새로고침"}
        </button>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded border p-4">
          <div className="text-sm text-gray-500">총자산 (KRW)</div>
          <div className="text-2xl font-semibold">₩{krw(s.total_value_krw)}</div>
        </div>
        <div className="rounded border p-4">
          <div className="text-sm text-gray-500">총손익</div>
          <div className={`text-2xl font-semibold ${s.total_profit_loss_krw >= 0 ? "text-red-600" : "text-blue-600"}`}>
            ₩{krw(s.total_profit_loss_krw)} ({s.total_profit_loss_pct.toFixed(2)}%)
          </div>
        </div>
      </div>
      <table className="w-full text-sm border-collapse">
        <thead><tr className="border-b text-left text-gray-500">
          <th className="py-2">종목</th><th>수량</th><th>평단</th><th>현재가</th>
          <th>평가액(KRW)</th><th>손익</th><th>비중</th><th></th>
        </tr></thead>
        <tbody>
          {data.positions.map((p) => (
            <tr key={p.asset_id} className="border-b">
              <td className="py-2">{p.name} <span className="text-gray-400">{p.ticker}·{p.market}</span></td>
              <td>{p.quantity}</td><td>{p.avg_price.toLocaleString()}</td>
              <td>{p.current_price.toLocaleString()}</td><td>₩{krw(p.value_krw)}</td>
              <td className={p.profit_loss_krw >= 0 ? "text-red-600" : "text-blue-600"}>
                ₩{krw(p.profit_loss_krw)} ({p.profit_loss_pct.toFixed(1)}%)
              </td>
              <td>{p.weight_pct.toFixed(1)}%</td>
              <td>{p.price_status !== "ok" && <span className="text-amber-600">⚠{p.price_status}</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
