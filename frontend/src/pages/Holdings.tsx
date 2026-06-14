import { useEffect, useState } from "react";
import { api } from "../api";
import type { ResolveResponse } from "../api";

const MARKETS = ["US", "KR", "JP", "CRYPTO"];
const ASSET_TYPES = [
  { code: "", label: "자동 감지" }, { code: "stock", label: "주식" },
  { code: "etf", label: "ETF" }, { code: "bond", label: "채권 (수동가격)" },
  { code: "commodity", label: "원자재" }, { code: "crypto", label: "가상자산" },
];

export default function Holdings() {
  const [assets, setAssets] = useState<any[]>([]);
  const [holdings, setHoldings] = useState<any[]>([]);
  // 신규 등록(통합) 입력
  const [ticker, setTicker] = useState(""); const [market, setMarket] = useState("US");
  const [assetType, setAssetType] = useState("");
  const [preview, setPreview] = useState<ResolveResponse | null>(null);
  const [lot, setLot] = useState<any>({ quantity: "", purchase_price: "", purchase_date: "", fee: "", memo: "" });
  // 기존 자산에 분할매수
  const [existForm, setExistForm] = useState<any>({ asset_id: "", quantity: "", purchase_price: "", purchase_date: "", fee: "", memo: "" });

  const load = async () => { setAssets(await api.listAssets()); setHoldings(await api.listHoldings()); };
  useEffect(() => { load(); }, []);

  const doResolve = async () => setPreview(await api.resolve(ticker, market, assetType || undefined));

  const addNew = async () => {
    if (!preview?.asset) return;
    await api.createHoldingWithAsset({
      ...preview.asset,
      quantity: Number(lot.quantity), purchase_price: Number(lot.purchase_price),
      purchase_date: lot.purchase_date || null, fee: Number(lot.fee || 0), memo: lot.memo || null,
    });
    setPreview(null); setTicker(""); setLot({ quantity: "", purchase_price: "", purchase_date: "", fee: "", memo: "" });
    await load();
  };

  const addExisting = async () => {
    await api.createHolding({
      asset_id: Number(existForm.asset_id), quantity: Number(existForm.quantity),
      purchase_price: Number(existForm.purchase_price), purchase_date: existForm.purchase_date || null,
      fee: Number(existForm.fee || 0), memo: existForm.memo || null,
    });
    setExistForm({ asset_id: "", quantity: "", purchase_price: "", purchase_date: "", fee: "", memo: "" });
    await load();
  };

  const remove = async (id: number) => { await api.deleteHolding(id); await load(); };

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold">보유종목 추가</h1>

      {/* 신규: 조회 → 등록 한 흐름 */}
      <section className="space-y-2">
        <div className="flex gap-2 items-center flex-wrap">
          <input className="border rounded px-2 py-1" placeholder="티커 (AAPL, 005930, BTC, GC=F)"
            value={ticker} onChange={(e) => setTicker(e.target.value)} />
          <select className="border rounded px-2 py-1" value={market} onChange={(e) => setMarket(e.target.value)}>
            {MARKETS.map((m) => <option key={m}>{m}</option>)}
          </select>
          <select className="border rounded px-2 py-1" value={assetType} onChange={(e) => setAssetType(e.target.value)}>
            {ASSET_TYPES.map((t) => <option key={t.code} value={t.code}>{t.label}</option>)}
          </select>
          <button onClick={doResolve} className="px-3 py-1 rounded bg-gray-800 text-white">조회</button>
        </div>

        {preview && (preview.ok && preview.asset ? (
          <div className="rounded border p-3 bg-green-50 space-y-2">
            <div><b>{preview.asset.name}</b> · {preview.asset.currency} · {preview.asset.asset_type} · 현재가 {preview.asset.current_price ?? "—"}</div>
            <div className="flex gap-2 flex-wrap">
              <input className="border rounded px-2 py-1 w-24" placeholder="수량"
                value={lot.quantity} onChange={(e) => setLot({ ...lot, quantity: e.target.value })} />
              <input className="border rounded px-2 py-1 w-32" placeholder={`매입단가 (${preview.asset.currency})`}
                value={lot.purchase_price} onChange={(e) => setLot({ ...lot, purchase_price: e.target.value })} />
              <input type="date" className="border rounded px-2 py-1" title="매입일(선택)"
                value={lot.purchase_date} onChange={(e) => setLot({ ...lot, purchase_date: e.target.value })} />
              <input className="border rounded px-2 py-1 w-24" placeholder="수수료"
                value={lot.fee} onChange={(e) => setLot({ ...lot, fee: e.target.value })} />
              <input className="border rounded px-2 py-1" placeholder="메모"
                value={lot.memo} onChange={(e) => setLot({ ...lot, memo: e.target.value })} />
              <button onClick={addNew} className="px-3 py-1 rounded bg-blue-600 text-white">보유 추가</button>
            </div>
          </div>
        ) : (
          <div className="rounded border p-3 bg-amber-50">
            <div>조회 실패 (시도: {preview.tried.join(", ")})</div>
            <div className="text-sm text-gray-600">{preview.suggestion}</div>
          </div>
        ))}
      </section>

      {/* 기존 자산에 분할매수 */}
      <section className="space-y-2">
        <h2 className="font-semibold">기존 자산에 추가 매수</h2>
        <div className="flex gap-2 flex-wrap">
          <select className="border rounded px-2 py-1" value={existForm.asset_id}
            onChange={(e) => setExistForm({ ...existForm, asset_id: e.target.value })}>
            <option value="">자산 선택</option>
            {assets.map((a) => <option key={a.asset_id} value={a.asset_id}>{a.ticker}·{a.market} {a.name}</option>)}
          </select>
          <input className="border rounded px-2 py-1 w-24" placeholder="수량"
            value={existForm.quantity} onChange={(e) => setExistForm({ ...existForm, quantity: e.target.value })} />
          <input className="border rounded px-2 py-1 w-32" placeholder="매입단가"
            value={existForm.purchase_price} onChange={(e) => setExistForm({ ...existForm, purchase_price: e.target.value })} />
          <input type="date" className="border rounded px-2 py-1" title="매입일(선택)"
            value={existForm.purchase_date} onChange={(e) => setExistForm({ ...existForm, purchase_date: e.target.value })} />
          <input className="border rounded px-2 py-1 w-24" placeholder="수수료"
            value={existForm.fee} onChange={(e) => setExistForm({ ...existForm, fee: e.target.value })} />
          <button onClick={addExisting} className="px-3 py-1 rounded bg-blue-600 text-white">추가</button>
        </div>
      </section>

      {/* 보유 목록 */}
      <section>
        <h2 className="font-semibold">보유 목록</h2>
        <table className="w-full text-sm mt-2">
          <thead><tr className="border-b text-left text-gray-500">
            <th className="py-2">자산ID</th><th>매입일</th><th>수량</th><th>단가</th><th></th>
          </tr></thead>
          <tbody>
            {holdings.map((h) => (
              <tr key={h.holding_id} className="border-b">
                <td className="py-2">{h.asset_id}</td><td>{h.purchase_date ?? "—"}</td>
                <td>{h.quantity}</td><td>{h.purchase_price}</td>
                <td><button onClick={() => remove(h.holding_id)} className="text-red-600">삭제</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
