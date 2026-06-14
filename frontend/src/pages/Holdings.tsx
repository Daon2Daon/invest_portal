import { useEffect, useState } from "react";
import { api } from "../api";

export default function Holdings() {
  const [assets, setAssets] = useState<any[]>([]); const [holdings, setHoldings] = useState<any[]>([]);
  const [form, setForm] = useState<any>({ asset_id: "", purchase_date: "", quantity: "", purchase_price: "", fee: "", memo: "" });
  const load = async () => { setAssets(await api.listAssets()); setHoldings(await api.listHoldings()); };
  useEffect(() => { load(); }, []);

  const submit = async () => {
    await api.createHolding({ ...form, asset_id: Number(form.asset_id),
      quantity: Number(form.quantity), purchase_price: Number(form.purchase_price), fee: Number(form.fee) });
    setForm({ asset_id: "", purchase_date: "", quantity: "", purchase_price: "", fee: "", memo: "" });
    await load();
  };
  const remove = async (id: number) => { await api.deleteHolding(id); await load(); };

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-xl font-bold">보유 관리 (lot)</h1>
      <div className="grid grid-cols-3 gap-2 max-w-3xl">
        <select className="border rounded px-2 py-1" value={form.asset_id}
          onChange={(e) => setForm({ ...form, asset_id: e.target.value })}>
          <option value="">자산 선택</option>
          {assets.map((a) => <option key={a.asset_id} value={a.asset_id}>{a.ticker}·{a.market} {a.name}</option>)}
        </select>
        <input type="date" className="border rounded px-2 py-1" value={form.purchase_date}
          onChange={(e) => setForm({ ...form, purchase_date: e.target.value })} />
        <input placeholder="수량" className="border rounded px-2 py-1" value={form.quantity}
          onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
        <input placeholder="매입단가(자산통화)" className="border rounded px-2 py-1" value={form.purchase_price}
          onChange={(e) => setForm({ ...form, purchase_price: e.target.value })} />
        <input placeholder="수수료" className="border rounded px-2 py-1" value={form.fee}
          onChange={(e) => setForm({ ...form, fee: e.target.value })} />
        <input placeholder="메모" className="border rounded px-2 py-1" value={form.memo}
          onChange={(e) => setForm({ ...form, memo: e.target.value })} />
      </div>
      <button onClick={submit} className="px-3 py-1 rounded bg-blue-600 text-white">추가</button>

      <table className="w-full text-sm mt-4">
        <thead><tr className="border-b text-left text-gray-500">
          <th className="py-2">자산ID</th><th>매입일</th><th>수량</th><th>단가</th><th></th>
        </tr></thead>
        <tbody>
          {holdings.map((h) => (
            <tr key={h.holding_id} className="border-b">
              <td className="py-2">{h.asset_id}</td><td>{h.purchase_date}</td>
              <td>{h.quantity}</td><td>{h.purchase_price}</td>
              <td><button onClick={() => remove(h.holding_id)} className="text-red-600">삭제</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
