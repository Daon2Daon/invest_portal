import { useEffect, useState } from "react";
import { api } from "../api";
import type { ReportRow } from "../api";

export default function Reports() {
  const [rows, setRows] = useState<ReportRow[]>([]);
  const [selected, setSelected] = useState<ReportRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const load = async () => {
    try { setRows(await api.listReports()); }
    catch (e) { setError(String(e)); }
  };
  useEffect(() => { load(); }, []);

  const generate = async () => {
    setLoading(true); setError(""); setMsg("");
    try {
      const r = await api.createReport();
      await load();
      setSelected(r);
    } catch (e) {
      const s = String(e);
      setError(s.includes("409") ? "설정에서 AI 리포트를 활성화하고 게이트웨이·모델을 입력하세요." : s);
    } finally { setLoading(false); }
  };

  const remove = async (id: number) => {
    await api.deleteReport(id);
    if (selected?.id === id) setSelected(null);
    await load();
  };

  const send = async (id: number) => {
    setMsg(""); setError("");
    try { const r = await api.sendReportTelegram(id); setMsg(`텔레그램 발송 완료 (${r.sent}건)`); }
    catch (e) { setError(String(e).includes("409") ? "텔레그램이 설정되지 않았습니다." : String(e)); }
  };

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">AI 리포트</h1>
        <button className="btn btn-primary" onClick={generate} disabled={loading}>
          {loading ? "생성 중…" : "리포트 생성"}
        </button>
      </div>
      {error && <div className="card text-sm" style={{ color: "var(--down)" }}>{error}</div>}
      {msg && <div className="card text-sm">{msg}</div>}

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        <div className="card space-y-1">
          {rows.length === 0 && <p className="text-sm text-muted">아직 생성된 리포트가 없습니다.</p>}
          {rows.map((r) => (
            <div key={r.id}
                 className={`flex items-center justify-between rounded px-2 py-1 cursor-pointer ${selected?.id === r.id ? "badge" : ""}`}
                 onClick={() => setSelected(r)}>
              <div className="min-w-0">
                <div className="truncate text-sm">{r.title}</div>
                <div className="text-xs text-muted">
                  {r.created_at?.slice(0, 16).replace("T", " ")} · {r.trigger}
                </div>
              </div>
              <button className="btn btn-ghost text-xs" onClick={(e) => { e.stopPropagation(); remove(r.id); }}>삭제</button>
            </div>
          ))}
        </div>

        <div className="card">
          {selected ? (
            <>
              <div className="mb-2 flex items-center justify-between">
                <h2 className="font-semibold">{selected.title}</h2>
                <button className="btn text-sm" onClick={() => send(selected.id)}>텔레그램 발송</button>
              </div>
              <div className="whitespace-pre-wrap text-sm leading-relaxed">{selected.content_md}</div>
            </>
          ) : (
            <p className="text-sm text-muted">왼쪽에서 리포트를 선택하거나 새로 생성하세요.</p>
          )}
        </div>
      </div>
    </div>
  );
}
