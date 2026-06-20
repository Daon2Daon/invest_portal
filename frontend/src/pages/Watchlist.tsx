import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { WatchlistItem, ResolveResponse } from "../api";

const MARKETS = ["US", "KR", "JP", "CRYPTO"];
const ASSET_TYPES = [
  { code: "", label: "자동 감지" }, { code: "stock", label: "주식" },
  { code: "etf", label: "ETF" }, { code: "bond", label: "채권 (수동가격)" },
  { code: "commodity", label: "원자재" }, { code: "crypto", label: "가상자산" },
];

export default function Watchlist() {
  const nav = useNavigate();
  const [rows, setRows] = useState<WatchlistItem[]>([]);
  const [ticker, setTicker] = useState(""); const [market, setMarket] = useState("US");
  const [assetType, setAssetType] = useState("");
  const [preview, setPreview] = useState<ResolveResponse | null>(null);
  const [msg, setMsg] = useState("");

  const load = async () => setRows(await api.listWatchlist());
  useEffect(() => { load(); }, []);

  const doResolve = async () => {
    setMsg("");
    setPreview(await api.resolve(ticker, market, assetType || undefined));
  };
  const addWatch = async () => {
    if (!preview?.asset) return;
    try {
      await api.createWatchlistAsset(preview.asset);
      setPreview(null); setTicker(""); setMsg("추가됨");
      await load();
    } catch (e: any) { setMsg("추가 실패: " + e.message); }
  };
  const remove = async (id: number) => {
    if (!confirm("이 관심종목을 삭제할까요?")) return;
    try {
      await api.deleteAsset(id); await load();
    } catch (e: any) { setMsg("삭제 실패: " + e.message); }
  };

  const pct = (n: number | null) =>
    n == null ? "—" : <span className={n >= 0 ? "text-up" : "text-down"}>{n >= 0 ? "+" : ""}{n.toFixed(2)}%</span>;

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold">관심종목</h1>

      <section className="space-y-2">
        <h2 className="font-semibold text-muted">관심종목 추가</h2>
        <div className="flex gap-2 items-center flex-wrap">
          <input className="input" placeholder="티커 (AAPL, 005930, BTC, GC=F)"
            value={ticker} onChange={(e) => setTicker(e.target.value)} />
          <select className="input" value={market} onChange={(e) => setMarket(e.target.value)}>
            {MARKETS.map((m) => <option key={m}>{m}</option>)}
          </select>
          <select className="input" value={assetType} onChange={(e) => setAssetType(e.target.value)}>
            {ASSET_TYPES.map((t) => <option key={t.code} value={t.code}>{t.label}</option>)}
          </select>
          <button onClick={doResolve} className="btn">조회</button>
          {msg && <span className="text-sm text-muted">{msg}</span>}
        </div>
        {preview && (preview.ok && preview.asset ? (
          <div className="rounded border border-border p-3 bg-green-50 flex items-center gap-3 flex-wrap">
            <div><b>{preview.asset.name}</b> · {preview.asset.currency} · {preview.asset.asset_type} · 현재가 {preview.asset.current_price ?? "—"}</div>
            <button onClick={addWatch} className="btn btn-primary">관심 추가</button>
          </div>
        ) : (
          <div className="rounded border border-border p-3 bg-amber-50">
            <div>조회 실패 (시도: {preview.tried.join(", ")})</div>
            <div className="text-sm text-muted">{preview.suggestion}</div>
          </div>
        ))}
      </section>

      <table className="w-full text-sm border-collapse">
        <thead><tr className="border-b border-border text-left text-muted">
          <th className="py-2">종목</th><th>현재가</th><th>변화</th><th>자산군</th><th></th>
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.asset_id} className="border-b border-border hover:bg-surface-2 cursor-pointer"
              onClick={() => nav(`/asset/${r.asset_id}`)}>
              <td className="py-2">{r.name} <span className="text-muted">{r.ticker}·{r.market}</span></td>
              <td>{r.current_price == null
                ? <span className="text-amber-600">⚠{r.price_status}</span>
                : r.current_price.toLocaleString()}</td>
              <td>{pct(r.change_pct)}</td>
              <td>{r.asset_class ?? "—"}</td>
              <td className="whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                <button onClick={() => remove(r.asset_id)} className="text-red-600">삭제</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
