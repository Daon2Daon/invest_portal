import { useEffect, useState } from "react";
import { api } from "../api";
import type { ResolveResponse } from "../api";

const MARKETS = ["US", "KR", "JP", "CRYPTO"];

// 표시명 → 저장 코드. 빈 값은 "자동 감지"(데이터 소스가 유형 판별).
const ASSET_TYPES: { code: string; label: string }[] = [
  { code: "", label: "자동 감지" },
  { code: "stock", label: "주식" },
  { code: "etf", label: "ETF" },
  { code: "bond", label: "채권 (수동가격)" },
  { code: "commodity", label: "원자재" },
  { code: "crypto", label: "가상자산" },
];

export default function Assets() {
  const [ticker, setTicker] = useState(""); const [market, setMarket] = useState("US");
  const [assetType, setAssetType] = useState(""); const [preview, setPreview] = useState<ResolveResponse | null>(null);
  const [assets, setAssets] = useState<any[]>([]);
  const load = async () => setAssets(await api.listAssets());
  useEffect(() => { load(); }, []);

  const doResolve = async () =>
    setPreview(await api.resolve(ticker, market, assetType || undefined));
  const confirm = async () => {
    if (!preview?.asset) return;
    await api.createAsset(preview.asset);
    setPreview(null); setTicker(""); await load();
  };

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-xl font-bold">자산 등록</h1>
      <div className="flex gap-2 items-center">
        <input className="border rounded px-2 py-1" placeholder="티커 (AAPL, 005930, 7203, BTC)"
          value={ticker} onChange={(e) => setTicker(e.target.value)} />
        <select className="border rounded px-2 py-1" value={market} onChange={(e) => setMarket(e.target.value)}>
          {MARKETS.map((m) => <option key={m}>{m}</option>)}
        </select>
        <select className="border rounded px-2 py-1" value={assetType}
          onChange={(e) => setAssetType(e.target.value)}>
          {ASSET_TYPES.map((t) => <option key={t.code} value={t.code}>{t.label}</option>)}
        </select>
        <button onClick={doResolve} className="px-3 py-1 rounded bg-gray-800 text-white">조회</button>
      </div>

      {preview && (preview.ok && preview.asset ? (
        <div className="rounded border p-3 bg-green-50">
          <div><b>{preview.asset.name}</b> · {preview.asset.currency} · {preview.asset.asset_type} · {preview.asset.data_source}</div>
          <div>현재가: {preview.asset.current_price ?? "—"}</div>
          <button onClick={confirm} className="mt-2 px-3 py-1 rounded bg-blue-600 text-white">등록</button>
        </div>
      ) : (
        <div className="rounded border p-3 bg-amber-50">
          <div>조회 실패 (시도: {preview.tried.join(", ")})</div>
          <div className="text-sm text-gray-600">{preview.suggestion}</div>
        </div>
      ))}

      <h2 className="font-semibold mt-4">등록된 자산</h2>
      <ul className="text-sm">
        {assets.map((a) => <li key={a.asset_id}>{a.ticker}·{a.market} — {a.name} · {a.asset_type} ({a.data_source})</li>)}
      </ul>
    </div>
  );
}
