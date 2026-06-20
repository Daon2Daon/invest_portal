import { useEffect, useState } from "react";
import { api, ASSET_CLASSES } from "../api";
import type { ResolveResponse } from "../api";

const MARKETS = ["US", "KR", "JP", "CRYPTO"];
const CURRENCIES = ["KRW", "USD", "JPY"];
const ASSET_TYPES = [
  { code: "", label: "자동 감지" }, { code: "stock", label: "주식" },
  { code: "etf", label: "ETF" }, { code: "bond", label: "채권 (수동가격)" },
  { code: "commodity", label: "원자재" }, { code: "crypto", label: "가상자산" },
];

const emptyLot = { quantity: "", purchase_price: "", purchase_date: "", fee: "", memo: "", asset_class: "" };
const emptyCash = { currency: "KRW", amount: "", label: "" };

export default function Holdings() {
  const [assets, setAssets] = useState<any[]>([]);
  const [holdings, setHoldings] = useState<any[]>([]);
  const [cash, setCash] = useState<any[]>([]);
  const [ticker, setTicker] = useState(""); const [market, setMarket] = useState("US");
  const [assetType, setAssetType] = useState("");
  const [preview, setPreview] = useState<ResolveResponse | null>(null);
  const [lot, setLot] = useState<any>({ ...emptyLot });
  const [cashForm, setCashForm] = useState<any>({ ...emptyCash });
  const [editHid, setEditHid] = useState<number | null>(null);
  const [editH, setEditH] = useState<any>({ ...emptyLot });
  const [editCid, setEditCid] = useState<number | null>(null);
  const [editC, setEditC] = useState<any>({ ...emptyCash });

  const load = async () => {
    setAssets(await api.listAssets());
    setHoldings(await api.listHoldings());
    setCash(await api.listCash());
  };
  useEffect(() => { load(); }, []);

  const assetById = Object.fromEntries(assets.map((a) => [a.asset_id, a]));

  const doResolve = async () => {
    const res = await api.resolve(ticker, market, assetType || undefined);
    setPreview(res);
    if (res.ok && res.asset) setLot({ ...emptyLot, asset_class: res.asset.asset_class ?? "" });
  };
  const addNew = async () => {
    if (!preview?.asset) return;
    await api.createHoldingWithAsset({
      ...preview.asset, asset_class: lot.asset_class || null,
      quantity: Number(lot.quantity), purchase_price: Number(lot.purchase_price),
      purchase_date: lot.purchase_date || null, fee: Number(lot.fee || 0), memo: lot.memo || null,
    });
    setPreview(null); setTicker(""); setLot({ ...emptyLot });
    await load();
  };

  const addCash = async () => {
    await api.createCash({ currency: cashForm.currency, amount: Number(cashForm.amount), label: cashForm.label || null });
    setCashForm({ ...emptyCash });
    await load();
  };

  const startEditH = (h: any) => {
    setEditHid(h.holding_id);
    setEditH({ quantity: h.quantity, purchase_price: h.purchase_price,
      purchase_date: h.purchase_date ?? "", fee: h.fee, memo: h.memo ?? "",
      asset_class: assetById[h.asset_id]?.asset_class ?? "" });
  };
  const saveH = async (h: any) => {
    await api.updateAsset(h.asset_id, { asset_class: editH.asset_class || null });
    await api.updateHolding(editHid!, {
      quantity: Number(editH.quantity), purchase_price: Number(editH.purchase_price),
      purchase_date: editH.purchase_date || null, fee: Number(editH.fee || 0), memo: editH.memo || null });
    setEditHid(null); await load();
  };
  const removeH = async (id: number) => { await api.deleteHolding(id); await load(); };

  const startEditC = (c: any) => { setEditCid(c.id); setEditC({ currency: c.currency, amount: c.amount, label: c.label ?? "" }); };
  const saveC = async () => {
    await api.updateCash(editCid!, { currency: editC.currency, amount: Number(editC.amount), label: editC.label || null });
    setEditCid(null); await load();
  };
  const removeC = async (id: number) => { await api.deleteCash(id); await load(); };

  return (
    <div className="p-6 space-y-8">
      <datalist id="asset-classes">{ASSET_CLASSES.map((c) => <option key={c} value={c} />)}</datalist>

      <div className="space-y-6">
        <h1 className="text-xl font-bold">보유 추가</h1>

        <section className="space-y-2">
          <h2 className="font-semibold text-muted">종목</h2>
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
          </div>
          {preview && (preview.ok && preview.asset ? (
            <div className="rounded border border-border p-3 bg-green-50 space-y-2">
              <div><b>{preview.asset.name}</b> · {preview.asset.currency} · {preview.asset.asset_type} · 현재가 {preview.asset.current_price ?? "—"}</div>
              <div className="flex gap-2 flex-wrap">
                <input className="input w-24" placeholder="수량"
                  value={lot.quantity} onChange={(e) => setLot({ ...lot, quantity: e.target.value })} />
                <input className="input w-32" placeholder={`매입단가 (${preview.asset.currency})`}
                  value={lot.purchase_price} onChange={(e) => setLot({ ...lot, purchase_price: e.target.value })} />
                <input type="date" className="input" title="매입일(선택)"
                  value={lot.purchase_date} onChange={(e) => setLot({ ...lot, purchase_date: e.target.value })} />
                <input className="input w-24" placeholder="수수료"
                  value={lot.fee} onChange={(e) => setLot({ ...lot, fee: e.target.value })} />
                <input list="asset-classes" className="input w-28" placeholder="자산군"
                  value={lot.asset_class} onChange={(e) => setLot({ ...lot, asset_class: e.target.value })} />
                <input className="input" placeholder="메모"
                  value={lot.memo} onChange={(e) => setLot({ ...lot, memo: e.target.value })} />
                <button onClick={addNew} className="btn btn-primary">추가</button>
              </div>
              <div className="text-xs text-muted">같은 티커를 다시 추가하면 기존 자산에 분할매수로 쌓입니다.</div>
            </div>
          ) : (
            <div className="rounded border border-border p-3 bg-amber-50">
              <div>조회 실패 (시도: {preview.tried.join(", ")})</div>
              <div className="text-sm text-muted">{preview.suggestion}</div>
            </div>
          ))}
        </section>

        <section className="space-y-2">
          <h2 className="font-semibold text-muted">현금</h2>
          <div className="flex gap-2 flex-wrap items-center">
            <select className="input" value={cashForm.currency}
              onChange={(e) => setCashForm({ ...cashForm, currency: e.target.value })}>
              {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
            </select>
            <input className="input w-40" placeholder="금액"
              value={cashForm.amount} onChange={(e) => setCashForm({ ...cashForm, amount: e.target.value })} />
            <input className="input" placeholder="라벨(예: 증권사 예수금)"
              value={cashForm.label} onChange={(e) => setCashForm({ ...cashForm, label: e.target.value })} />
            <button onClick={addCash} className="btn btn-primary">추가</button>
          </div>
        </section>
      </div>

      <section>
        <h2 className="font-semibold mb-2">보유 종목</h2>
        <table className="w-full text-sm">
          <thead><tr className="border-b border-border text-left text-muted">
            <th className="py-2">종목</th><th>자산군</th><th>매입일</th><th>수량</th><th>단가</th><th>수수료</th><th>메모</th><th></th>
          </tr></thead>
          <tbody>
            {holdings.map((h) => {
              const a = assetById[h.asset_id];
              const editing = editHid === h.holding_id;
              return (
                <tr key={h.holding_id} className="border-b border-border">
                  <td className="py-2">{a ? `${a.name} (${a.ticker}·${a.market})` : `#${h.asset_id}`}</td>
                  {editing ? (
                    <>
                      <td><input list="asset-classes" className="input w-24" value={editH.asset_class}
                        onChange={(e) => setEditH({ ...editH, asset_class: e.target.value })} /></td>
                      <td><input type="date" className="input w-36" value={editH.purchase_date}
                        onChange={(e) => setEditH({ ...editH, purchase_date: e.target.value })} /></td>
                      <td><input className="input w-20" value={editH.quantity}
                        onChange={(e) => setEditH({ ...editH, quantity: e.target.value })} /></td>
                      <td><input className="input w-24" value={editH.purchase_price}
                        onChange={(e) => setEditH({ ...editH, purchase_price: e.target.value })} /></td>
                      <td><input className="input w-20" value={editH.fee}
                        onChange={(e) => setEditH({ ...editH, fee: e.target.value })} /></td>
                      <td><input className="input w-28" value={editH.memo}
                        onChange={(e) => setEditH({ ...editH, memo: e.target.value })} /></td>
                      <td className="whitespace-nowrap">
                        <button onClick={() => saveH(h)} className="text-accent mr-2">저장</button>
                        <button onClick={() => setEditHid(null)} className="text-muted">취소</button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td>{a?.asset_class ?? "—"}</td>
                      <td>{h.purchase_date ?? "—"}</td><td>{h.quantity}</td><td>{h.purchase_price}</td>
                      <td>{h.fee}</td><td>{h.memo ?? "—"}</td>
                      <td className="whitespace-nowrap">
                        <button onClick={() => startEditH(h)} className="text-accent mr-2">수정</button>
                        <button onClick={() => removeH(h.holding_id)} className="text-red-600">삭제</button>
                      </td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <section>
        <h2 className="font-semibold mb-2">현금</h2>
        <table className="w-full text-sm">
          <thead><tr className="border-b border-border text-left text-muted">
            <th className="py-2">통화</th><th>금액</th><th>라벨</th><th></th>
          </tr></thead>
          <tbody>
            {cash.map((c) => {
              const editing = editCid === c.id;
              return (
                <tr key={c.id} className="border-b border-border">
                  {editing ? (
                    <>
                      <td className="py-2"><select className="input" value={editC.currency}
                        onChange={(e) => setEditC({ ...editC, currency: e.target.value })}>
                        {CURRENCIES.map((x) => <option key={x}>{x}</option>)}
                      </select></td>
                      <td><input className="input w-32" value={editC.amount}
                        onChange={(e) => setEditC({ ...editC, amount: e.target.value })} /></td>
                      <td><input className="input" value={editC.label}
                        onChange={(e) => setEditC({ ...editC, label: e.target.value })} /></td>
                      <td className="whitespace-nowrap">
                        <button onClick={saveC} className="text-accent mr-2">저장</button>
                        <button onClick={() => setEditCid(null)} className="text-muted">취소</button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="py-2">{c.currency}</td><td>{Number(c.amount).toLocaleString()}</td>
                      <td>{c.label ?? "—"}</td>
                      <td className="whitespace-nowrap">
                        <button onClick={() => startEditC(c)} className="text-accent mr-2">수정</button>
                        <button onClick={() => removeC(c.id)} className="text-red-600">삭제</button>
                      </td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}
