import { useEffect, useState } from "react";
import { api } from "../api";

const CURRENCIES = ["KRW", "USD", "JPY"];

export default function Cash() {
  const [rows, setRows] = useState<any[]>([]);
  const [form, setForm] = useState<any>({ currency: "KRW", amount: "", label: "", memo: "" });
  const load = async () => setRows(await api.listCash());
  useEffect(() => { load(); }, []);

  const add = async () => {
    await api.createCash({ currency: form.currency, amount: Number(form.amount),
      label: form.label || null, memo: form.memo || null });
    setForm({ currency: "KRW", amount: "", label: "", memo: "" });
    await load();
  };
  const remove = async (id: number) => { await api.deleteCash(id); await load(); };

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-xl font-bold">현금</h1>
      <div className="flex gap-2 flex-wrap items-center">
        <select className="border rounded px-2 py-1" value={form.currency}
          onChange={(e) => setForm({ ...form, currency: e.target.value })}>
          {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
        </select>
        <input className="border rounded px-2 py-1 w-40" placeholder="금액"
          value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        <input className="border rounded px-2 py-1" placeholder="라벨(예: 증권사 예수금)"
          value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
        <button onClick={add} className="px-3 py-1 rounded bg-blue-600 text-white">추가</button>
      </div>

      <table className="w-full text-sm">
        <thead><tr className="border-b text-left text-gray-500">
          <th className="py-2">통화</th><th>금액</th><th>라벨</th><th></th>
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b">
              <td className="py-2">{r.currency}</td><td>{Number(r.amount).toLocaleString()}</td>
              <td>{r.label ?? "—"}</td>
              <td><button onClick={() => remove(r.id)} className="text-red-600">삭제</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
