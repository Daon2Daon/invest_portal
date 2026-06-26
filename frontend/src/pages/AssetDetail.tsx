import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import type { AssetDetailOut, AlertView, JournalEntry, AssetAnalysis } from "../api";
import AlertForm, { BASIS_LABEL } from "../components/AlertForm";
import ReactMarkdown from "react-markdown";

const krw = (n: number) => n.toLocaleString("ko-KR", { maximumFractionDigits: 0 });
const DAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"];

export default function AssetDetail() {
  const { id } = useParams();
  const assetId = id ? Number(id) : null;

  const [detail, setDetail] = useState<AssetDetailOut | null>(null);
  const [nonce, setNonce] = useState(() => Date.now());
  const [msg, setMsg] = useState("");
  const [analyses, setAnalyses] = useState<AssetAnalysis[]>([]);
  const [openIds, setOpenIds] = useState<Set<number>>(new Set());
  const [analyzing, setAnalyzing] = useState(false);
  const [schedTime, setSchedTime] = useState("08:30");
  const [schedDays, setSchedDays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [schedEnabled, setSchedEnabled] = useState(false);
  const [schedMsg, setSchedMsg] = useState("");
  const [alerts, setAlerts] = useState<AlertView[]>([]);
  const [aMsg, setAMsg] = useState("");
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const [jForm, setJForm] = useState({ title: "", body: "" });
  const [jMsg, setJMsg] = useState("");

  useEffect(() => {
    if (!assetId) return;
    api.assetDetail(assetId).then(setDetail).catch(() => setDetail(null));
    api.getSchedule(assetId).then((s) => {
      if (s) { setSchedTime(s.send_time); setSchedDays(s.days_of_week); setSchedEnabled(s.enabled); }
      else { setSchedTime("08:30"); setSchedDays([0, 1, 2, 3, 4]); setSchedEnabled(false); }
      setSchedMsg("");
    }).catch(() => {});
    api.listAlerts(assetId).then(setAlerts).catch(() => setAlerts([]));
    api.listJournal(assetId).then(setJournal).catch(() => setJournal([]));
    api.listAnalyses(assetId).then((rows) => {
      setAnalyses(rows);
      setOpenIds(new Set(rows[0] ? [rows[0].id] : []));   // 최신 1건만 펼침
    }).catch(() => setAnalyses([]));
  }, [assetId]);

  const send = async () => {
    if (!assetId) return;
    setMsg("발송 중…");
    try {
      const r: any = await api.sendChartTelegram(assetId);
      const extra = r.analysis_sent ? " + AI 분석" : "";
      setMsg(r.ok ? `텔레그램 발송 완료 (${r.sent}장${extra})` : "발송 실패");
    } catch (e: any) { setMsg("발송 실패: " + e.message); }
  };
  const analyze = async () => {
    if (!assetId) return;
    setAnalyzing(true); setMsg("");
    try {
      await api.analyzeChart(assetId);
      const rows = await api.listAnalyses(assetId);
      setAnalyses(rows);
      setOpenIds(new Set(rows[0] ? [rows[0].id] : []));   // 최신 1건 펼침
    } catch (e: any) {
      setMsg("분석 실패: " + e.message);
    } finally {
      setAnalyzing(false);
    }
  };
  const toggleAnalysis = (id: number) =>
    setOpenIds((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  const removeAnalysis = async (id: number) => {
    try {
      await api.deleteAnalysis(id);
      setAnalyses((rows) => rows.filter((r) => r.id !== id));
    } catch (e: any) { setMsg("삭제 실패: " + e.message); }
  };
  const toggleDay = (d: number) =>
    setSchedDays((prev) => prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort());
  const saveSched = async () => {
    if (!assetId) return;
    setSchedMsg("저장 중…");
    try { await api.saveSchedule(assetId, { send_time: schedTime, days_of_week: schedDays, enabled: schedEnabled }); setSchedMsg("저장됨"); }
    catch (e: any) { setSchedMsg("저장 실패: " + e.message); }
  };
  const deleteSched = async () => {
    if (!assetId) return;
    setSchedMsg("삭제 중…");
    try { await api.deleteSchedule(assetId); setSchedEnabled(false); setSchedMsg("삭제됨"); }
    catch (e: any) { setSchedMsg("삭제 실패: " + e.message); }
  };
  const src = (period: "daily" | "weekly") =>
    assetId ? `${api.chartUrl(assetId, period)}&n=${nonce}` : "";

  const addJournal = async () => {
    if (!assetId || !jForm.title.trim()) { setJMsg("제목을 입력하세요."); return; }
    try {
      await api.createJournal({ asset_id: assetId, title: jForm.title, body: jForm.body || undefined });
      setJForm({ title: "", body: "" });
      setJMsg("저장됨");
      setJournal(await api.listJournal(assetId));
    } catch (e) { setJMsg(String(e)); }
  };
  const removeJournal = async (jid: number) => {
    await api.deleteJournal(jid);
    if (assetId) setJournal(await api.listJournal(assetId));
  };

  const reloadAlerts = async () => { if (assetId) setAlerts(await api.listAlerts(assetId)); };
  const rearm = async (id: number) => {
    try { await api.rearmAlert(id); await reloadAlerts(); }
    catch (e: any) { setAMsg("재무장 실패: " + e.message); }
  };
  const delAlert = async (id: number) => {
    try { await api.deleteAlert(id); await reloadAlerts(); }
    catch (e: any) { setAMsg("삭제 실패: " + e.message); }
  };

  if (!assetId) return <div className="p-6">잘못된 경로입니다.</div>;

  const a = detail?.asset;
  const q = detail?.quote;
  const hs = detail?.holding_summary;

  return (
    <div className="p-6 space-y-4">
      {a && (
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-xl font-bold">{a.name} <span className="text-muted text-base">{a.ticker}·{a.market}</span></h1>
          <span className={detail!.held ? "badge" : "bg-surface-2 text-muted px-2 py-0.5 rounded text-xs"}>
            {detail!.held ? "보유" : "관심"}
          </span>
          {q && q.status === "ok" && (
            <span className="text-lg">
              {q.price.toLocaleString()} {a.currency}
              {q.change_pct != null && (
                <span className={`ml-2 text-sm ${q.change_pct >= 0 ? "text-up" : "text-down"}`}>
                  {q.change_pct >= 0 ? "+" : ""}{q.change_pct.toFixed(2)}%
                </span>
              )}
            </span>
          )}
        </div>
      )}
      {hs && (
        <div className="text-sm text-muted">
          수량 {hs.quantity} · 평단 {hs.avg_price.toLocaleString()} · 평가손익 <span className={hs.profit_loss_krw >= 0 ? "text-up" : "text-down"}>₩{krw(hs.profit_loss_krw)} ({hs.profit_loss_pct.toFixed(1)}%)</span>
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        <button onClick={() => setNonce((n) => n + 1)} className="btn">새로고침</button>
        <button onClick={analyze} disabled={analyzing} className="btn">
          {analyzing ? "분석 중…" : "AI 분석"}
        </button>
        <button onClick={send} className="btn btn-primary">텔레그램 발송</button>
        {msg && <span className="text-sm text-muted">{msg}</span>}
      </div>

      {analyses.length > 0 && (
        <div className="space-y-2 max-w-3xl">
          {analyses.map((row, idx) => {
            const open = openIds.has(row.id);
            const ts = new Date(row.created_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
            return (
              <div key={row.id} className="card bg-surface-2">
                <div className="flex items-center justify-between gap-2">
                  <button
                    className="flex items-center gap-2 text-left text-xs text-muted flex-1"
                    onClick={() => toggleAnalysis(row.id)}
                  >
                    <span>{open ? "▲" : "▼"}</span>
                    <span>{ts} · {row.trigger === "scheduled" ? "자동" : "수동"}{idx === 0 ? " · 최신" : ""}</span>
                  </button>
                  <button
                    className="text-xs text-muted hover:text-down"
                    onClick={() => removeAnalysis(row.id)}
                  >삭제</button>
                </div>
                {open && (
                  <div className="prose prose-sm prose-invert max-w-none mt-2 text-sm leading-relaxed
                                  [&_h1]:font-semibold [&_h1]:text-base [&_h1]:mt-3
                                  [&_h2]:font-semibold [&_h2]:mt-3 [&_h3]:font-semibold [&_h3]:mt-2
                                  [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5
                                  [&_strong]:font-semibold [&_code]:text-accent">
                    <ReactMarkdown>{row.content_md}</ReactMarkdown>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <section className="card space-y-2">
        <h2 className="font-semibold text-muted">투자 메모</h2>
        <input className="input w-full" placeholder="제목" value={jForm.title}
               onChange={(e) => setJForm({ ...jForm, title: e.target.value })} />
        <textarea className="input w-full h-24" placeholder="이 종목에 대한 메모(마크다운)" value={jForm.body}
                  onChange={(e) => setJForm({ ...jForm, body: e.target.value })} />
        <div className="flex items-center gap-2">
          <button className="btn btn-primary" onClick={addJournal}>메모 추가</button>
          {jMsg && <span className="text-sm text-muted">{jMsg}</span>}
        </div>
        <div className="space-y-1">
          {journal.length === 0 && <p className="text-sm text-muted">이 종목에 대한 메모가 없습니다.</p>}
          {journal.map((e) => (
            <div key={e.id} className="border-t pt-1" style={{ borderColor: "var(--border)" }}>
              <div className="flex items-center justify-between">
                <span className="text-sm"><span className="text-muted">{e.entry_date}</span> <span className="font-semibold">{e.title}</span></span>
                <button className="btn btn-ghost text-xs" onClick={() => removeJournal(e.id)}>삭제</button>
              </div>
              {e.body && <div className="whitespace-pre-wrap text-sm">{e.body}</div>}
            </div>
          ))}
        </div>
      </section>

      <div className="space-y-6">
        <div>
          <h2 className="font-semibold mb-1">일봉</h2>
          <img src={src("daily")} alt="daily chart" className="max-w-full border rounded"
            onError={(e) => ((e.target as HTMLImageElement).alt = "차트를 가져올 수 없습니다(수동/이력없음 자산일 수 있음)")} />
        </div>
        <div>
          <h2 className="font-semibold mb-1">주봉</h2>
          <img src={src("weekly")} alt="weekly chart" className="max-w-full border rounded"
            onError={(e) => ((e.target as HTMLImageElement).alt = "차트를 가져올 수 없습니다(수동/이력없음 자산일 수 있음)")} />
        </div>
      </div>

      <div className="card max-w-3xl space-y-3">
        <h2 className="font-semibold text-muted">가격 알림</h2>
        <AlertForm
          fixed={{ asset_id: assetId, held: !!detail?.held, manual: detail?.asset.data_source === "manual" }}
          onAdded={reloadAlerts}
        />
        {aMsg && <span className="text-sm text-muted">{aMsg}</span>}
        <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse whitespace-nowrap">
          <thead><tr className="border-b border-border text-left text-muted">
            <th className="py-1">기준</th><th>방향</th><th>값</th><th>현재 목표가</th><th>상태</th><th></th>
          </tr></thead>
          <tbody>
            {alerts.map((al) => (
              <tr key={al.alert_id} className="border-b border-border">
                <td className="py-1">{BASIS_LABEL[al.basis]}</td>
                <td>{al.basis === "REFERENCE" ? `±${al.value}%` : (al.direction === "ABOVE" ? "이상" : "이하")}</td>
                <td>{al.basis === "REFERENCE" ? "—" : <>{al.value}{al.basis === "ABSOLUTE" ? "" : "%"}</>}</td>
                <td>{al.basis === "REFERENCE"
                  ? (al.reference_price == null ? "산정 중" : `${al.reference_price.toLocaleString()} ±${al.value}%`)
                  : (al.target_price == null ? "—" : al.target_price.toLocaleString())}</td>
                <td>{al.is_triggered
                  ? <span className="text-muted">발동됨</span>
                  : <span className="text-up">활성</span>}</td>
                <td className="whitespace-nowrap">
                  {al.is_triggered && (
                    <button onClick={() => rearm(al.alert_id)} className="text-accent mr-2">재무장</button>
                  )}
                  <button onClick={() => delAlert(al.alert_id)} className="text-up">삭제</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>

      <div className="card max-w-3xl space-y-2">
        <h2 className="font-semibold text-muted">자동 발송 스케줄</h2>
        <div className="flex items-center gap-2 flex-wrap">
          <label className="text-sm">발송 시각</label>
          <input type="time" className="input" value={schedTime} onChange={(e) => setSchedTime(e.target.value)} />
          <span className="text-xs text-muted">(KST)</span>
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          {DAY_LABELS.map((lbl, d) => (
            <button key={d} type="button" onClick={() => toggleDay(d)}
              className={schedDays.includes(d) ? "btn btn-primary" : "btn"}>{lbl}</button>
          ))}
        </div>
        <label className="flex gap-2 items-center text-sm">
          <input type="checkbox" checked={schedEnabled} onChange={(e) => setSchedEnabled(e.target.checked)} />
          스케줄 활성화
        </label>
        <div className="flex gap-2 items-center">
          <button onClick={saveSched} className="btn btn-primary">저장</button>
          <button onClick={deleteSched} className="btn">삭제</button>
          {schedMsg && <span className="text-sm text-muted">{schedMsg}</span>}
        </div>
      </div>
    </div>
  );
}
