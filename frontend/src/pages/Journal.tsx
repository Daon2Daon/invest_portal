import { useEffect, useState } from "react";
import { api, type JournalEntry } from "../api";

export default function Journal() {
  const [rows, setRows] = useState<JournalEntry[]>([]);
  const [assets, setAssets] = useState<any[]>([]);
  const [form, setForm] = useState({ entry_date: "", title: "", body: "", asset_id: "" });
  const [editing, setEditing] = useState<number | null>(null);
  const [edit, setEdit] = useState({ title: "", body: "", asset_id: "" });
  const [error, setError] = useState("");

  const load = async () => {
    try { setRows(await api.listJournal()); } catch (e) { setError(String(e)); }
  };
  useEffect(() => {
    load();
    api.listAssets().then(setAssets).catch(() => setAssets([]));
  }, []);

  const create = async () => {
    setError("");
    if (!form.title.trim()) { setError("제목을 입력하세요."); return; }
    try {
      await api.createJournal({
        title: form.title, body: form.body || undefined,
        asset_id: form.asset_id ? Number(form.asset_id) : null,
        entry_date: form.entry_date || undefined,
      });
      setForm({ entry_date: "", title: "", body: "", asset_id: "" });
      await load();
    } catch (e) { setError(String(e)); }
  };

  const startEdit = (r: JournalEntry) => {
    setEditing(r.id);
    setEdit({ title: r.title, body: r.body ?? "", asset_id: r.asset_id != null ? String(r.asset_id) : "" });
  };
  const saveEdit = async (id: number) => {
    try {
      await api.updateJournal(id, {
        title: edit.title, body: edit.body,
        asset_id: edit.asset_id ? Number(edit.asset_id) : null,
      });
      setEditing(null);
      await load();
    } catch (e) { setError(String(e)); }
  };
  const remove = async (id: number) => { await api.deleteJournal(id); await load(); };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">투자 저널</h1>
      {error && <div className="card text-sm" style={{ color: "var(--down)" }}>{error}</div>}

      <section className="card space-y-2">
        <h2 className="font-semibold">새 기록</h2>
        <div className="flex flex-wrap gap-2">
          <input className="input" type="date" value={form.entry_date}
                 onChange={(e) => setForm({ ...form, entry_date: e.target.value })} />
          <select className="input" value={form.asset_id}
                  onChange={(e) => setForm({ ...form, asset_id: e.target.value })}>
            <option value="">연결 안 함</option>
            {assets.map((a) => (
              <option key={a.asset_id} value={a.asset_id}>{a.name} ({a.ticker})</option>
            ))}
          </select>
        </div>
        <input className="input w-full" placeholder="제목" value={form.title}
               onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <textarea className="input w-full h-28" placeholder="본문(마크다운)" value={form.body}
                  onChange={(e) => setForm({ ...form, body: e.target.value })} />
        <button className="btn btn-primary" onClick={create}>저장</button>
      </section>

      <div className="space-y-2">
        {rows.length === 0 && <p className="text-sm text-muted">아직 기록이 없습니다.</p>}
        {rows.map((r) => (
          <div key={r.id} className="card space-y-1">
            {editing === r.id ? (
              <div className="space-y-2">
                <input className="input w-full" value={edit.title}
                       onChange={(e) => setEdit({ ...edit, title: e.target.value })} />
                <textarea className="input w-full h-28" value={edit.body}
                          onChange={(e) => setEdit({ ...edit, body: e.target.value })} />
                <select className="input" value={edit.asset_id}
                        onChange={(e) => setEdit({ ...edit, asset_id: e.target.value })}>
                  <option value="">연결 안 함</option>
                  {assets.map((a) => (
                    <option key={a.asset_id} value={a.asset_id}>{a.name} ({a.ticker})</option>
                  ))}
                </select>
                <div className="flex gap-2">
                  <button className="btn btn-primary" onClick={() => saveEdit(r.id)}>저장</button>
                  <button className="btn" onClick={() => setEditing(null)}>취소</button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <div className="text-sm">
                    <span className="text-muted">{r.entry_date}</span>{" "}
                    <span className="font-semibold">{r.title}</span>{" "}
                    {r.asset_name && <span className="badge">{r.asset_name} ({r.asset_ticker})</span>}
                  </div>
                  <div className="flex gap-2">
                    <button className="btn btn-ghost text-xs" onClick={() => startEdit(r)}>수정</button>
                    <button className="btn btn-ghost text-xs" onClick={() => remove(r.id)}>삭제</button>
                  </div>
                </div>
                {r.body && <div className="whitespace-pre-wrap text-sm">{r.body}</div>}
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
