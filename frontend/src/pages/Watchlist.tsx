import { Fragment, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { WatchlistItem, ResolveResponse, AlertRow } from "../api";

const MARKETS = ["US", "KR", "JP", "CRYPTO"];
const ASSET_TYPES = [
  { code: "", label: "자동 감지" }, { code: "stock", label: "주식" },
  { code: "etf", label: "ETF" }, { code: "bond", label: "채권 (수동가격)" },
  { code: "commodity", label: "원자재" }, { code: "crypto", label: "가상자산" },
];

const MARKET_ORDER = ["US", "KR", "JP", "CRYPTO"];
const CLASS_ORDER = ["주식", "채권", "현금성", "원자재", "가상자산", "대체투자", "기타"];
type GroupBy = "market" | "asset_class";

// 변화율 내림차순(움직임 큰 종목 먼저), 값 없는 항목(수동/조회실패)은 맨 뒤.
function byChangeDesc(a: WatchlistItem, b: WatchlistItem) {
  const av = a.change_pct, bv = b.change_pct;
  if (av == null && bv == null) return 0;
  if (av == null) return 1;
  if (bv == null) return -1;
  return bv - av;
}

function buildGroups(rows: WatchlistItem[], groupBy: GroupBy) {
  const order = groupBy === "market" ? MARKET_ORDER : CLASS_ORDER;
  const map = new Map<string, WatchlistItem[]>();
  for (const r of rows) {
    const key = groupBy === "market" ? r.market : (r.asset_class ?? "미분류");
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(r);
  }
  const rank = (k: string) => (order.indexOf(k) === -1 ? 999 : order.indexOf(k));
  return [...map.keys()]
    .sort((a, b) => (rank(a) !== rank(b) ? rank(a) - rank(b) : a.localeCompare(b)))
    .map((k) => ({ key: k, items: map.get(k)!.slice().sort(byChangeDesc) }));
}

export default function Watchlist() {
  const nav = useNavigate();
  const [rows, setRows] = useState<WatchlistItem[]>([]);
  const [ticker, setTicker] = useState(""); const [market, setMarket] = useState("US");
  const [assetType, setAssetType] = useState("");
  const [preview, setPreview] = useState<ResolveResponse | null>(null);
  const [msg, setMsg] = useState("");
  const [alertCount, setAlertCount] = useState<Record<number, number>>({});
  const [groupBy, setGroupBy] = useState<GroupBy>("market");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const load = async () => setRows(await api.listWatchlist());
  useEffect(() => {
    load();
    api.listAllAlerts().then((rows: AlertRow[]) => {
      const m: Record<number, number> = {};
      rows.forEach((r) => { if (r.enabled && !r.is_triggered) m[r.asset_id] = (m[r.asset_id] || 0) + 1; });
      setAlertCount(m);
    }).catch(() => {});
  }, []);

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

  const toggleCollapse = (k: string) =>
    setCollapsed((prev) => { const n = new Set(prev); n.has(k) ? n.delete(k) : n.add(k); return n; });

  const groups = buildGroups(rows, groupBy);

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
          <div className="rounded border border-border p-3 bg-ok-bg flex items-center gap-3 flex-wrap">
            <div><b>{preview.asset.name}</b> · {preview.asset.currency} · {preview.asset.asset_type} · 현재가 {preview.asset.current_price ?? "—"}</div>
            <button onClick={addWatch} className="btn btn-primary">관심 추가</button>
          </div>
        ) : (
          <div className="rounded border border-border p-3 bg-warn-bg">
            <div>조회 실패 (시도: {preview.tried.join(", ")})</div>
            <div className="text-sm text-muted">{preview.suggestion}</div>
          </div>
        ))}
      </section>

      <div className="flex items-center gap-2">
        <span className="text-sm text-muted">그룹:</span>
        <div className="flex gap-1">
          {([["market", "시장별"], ["asset_class", "자산군별"]] as const).map(([k, label]) => (
            <button key={k} onClick={() => setGroupBy(k)}
              className={`btn text-xs px-2 py-1 ${groupBy === k ? "btn-primary" : "btn-ghost"}`}>{label}</button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse whitespace-nowrap">
        <thead><tr className="border-b border-border text-left text-muted">
          <th className="py-2">종목</th><th>현재가</th><th>변화</th><th>자산군</th><th></th>
        </tr></thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={5} className="py-3 text-muted">등록된 관심종목이 없습니다.</td></tr>
          )}
          {groups.map((g) => (
            <Fragment key={g.key}>
              <tr className="cursor-pointer select-none" onClick={() => toggleCollapse(g.key)}>
                <td colSpan={5} className="pt-4 pb-1 font-semibold">
                  <span className="text-muted">{collapsed.has(g.key) ? "▸" : "▾"}</span>{" "}
                  {g.key}{" "}
                  <span className="text-muted font-normal text-xs">({g.items.length})</span>
                </td>
              </tr>
              {!collapsed.has(g.key) && g.items.map((r) => (
                <tr key={r.asset_id} className="border-b border-border hover:bg-surface-2 cursor-pointer"
                  onClick={() => nav(`/asset/${r.asset_id}`)}>
                  <td className="py-2">{r.name} <span className="text-muted">{r.ticker}·{r.market}</span>
                    {alertCount[r.asset_id] ? (
                      <span className="badge ml-2 cursor-pointer"
                        onClick={(e) => { e.stopPropagation(); nav("/alerts"); }}>🔔 {alertCount[r.asset_id]}</span>
                    ) : null}
                  </td>
                  <td>{r.current_price == null
                    ? <span className="text-amber-600">⚠{r.price_status}</span>
                    : r.current_price.toLocaleString()}</td>
                  <td>{pct(r.change_pct)}</td>
                  <td>{r.asset_class ?? "—"}</td>
                  <td className="whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                    <button onClick={() => remove(r.asset_id)} className="text-up">삭제</button>
                  </td>
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}
