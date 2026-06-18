import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import type { AssetDetailOut } from "../api";

const krw = (n: number) => n.toLocaleString("ko-KR", { maximumFractionDigits: 0 });
const DAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"];

export default function AssetDetail() {
  const { id } = useParams();
  const assetId = id ? Number(id) : null;

  const [detail, setDetail] = useState<AssetDetailOut | null>(null);
  const [nonce, setNonce] = useState(() => Date.now());
  const [msg, setMsg] = useState("");
  const [analysis, setAnalysis] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [schedTime, setSchedTime] = useState("08:30");
  const [schedDays, setSchedDays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [schedEnabled, setSchedEnabled] = useState(false);
  const [schedMsg, setSchedMsg] = useState("");

  useEffect(() => {
    if (!assetId) return;
    api.assetDetail(assetId).then(setDetail).catch(() => setDetail(null));
    api.getSchedule(assetId).then((s) => {
      if (s) { setSchedTime(s.send_time); setSchedDays(s.days_of_week); setSchedEnabled(s.enabled); }
      else { setSchedTime("08:30"); setSchedDays([0, 1, 2, 3, 4]); setSchedEnabled(false); }
      setSchedMsg("");
    });
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
    setAnalyzing(true); setAnalysis(""); setMsg("");
    try { setAnalysis((await api.analyzeChart(assetId)).analysis); }
    catch (e: any) { setAnalysis("분석 실패: " + e.message); }
    finally { setAnalyzing(false); }
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

  if (!assetId) return <div className="p-6">잘못된 경로입니다.</div>;

  const a = detail?.asset;
  const q = detail?.quote;
  const hs = detail?.holding_summary;

  return (
    <div className="p-6 space-y-4">
      {a && (
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-xl font-bold">{a.name} <span className="text-gray-400 text-base">{a.ticker}·{a.market}</span></h1>
          <span className={`px-2 py-0.5 rounded text-xs ${detail!.held ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-600"}`}>
            {detail!.held ? "보유" : "관심"}
          </span>
          {q && q.status === "ok" && (
            <span className="text-lg">
              {q.price.toLocaleString()} {a.currency}
              {q.change_pct != null && (
                <span className={`ml-2 text-sm ${q.change_pct >= 0 ? "text-red-600" : "text-blue-600"}`}>
                  {q.change_pct >= 0 ? "+" : ""}{q.change_pct.toFixed(2)}%
                </span>
              )}
            </span>
          )}
        </div>
      )}
      {hs && (
        <div className="text-sm text-gray-700">
          수량 {hs.quantity} · 평단 {hs.avg_price.toLocaleString()} · 평가손익 <span className={hs.profit_loss_krw >= 0 ? "text-red-600" : "text-blue-600"}>₩{krw(hs.profit_loss_krw)} ({hs.profit_loss_pct.toFixed(1)}%)</span>
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        <button onClick={() => setNonce((n) => n + 1)} className="px-3 py-1 rounded bg-gray-800 text-white">새로고침</button>
        <button onClick={analyze} disabled={analyzing} className="px-3 py-1 rounded bg-emerald-600 text-white disabled:opacity-50">
          {analyzing ? "분석 중…" : "AI 분석"}
        </button>
        <button onClick={send} className="px-3 py-1 rounded bg-blue-600 text-white">텔레그램 발송</button>
        {msg && <span className="text-sm text-gray-600">{msg}</span>}
      </div>

      {analysis && (
        <div className="border rounded p-3 bg-gray-50 whitespace-pre-wrap text-sm leading-relaxed max-w-3xl">{analysis}</div>
      )}

      <div className="border rounded p-3 bg-white max-w-3xl space-y-2">
        <h2 className="font-semibold text-gray-700">자동 발송 스케줄</h2>
        <div className="flex items-center gap-2 flex-wrap">
          <label className="text-sm">발송 시각</label>
          <input type="time" className="border rounded px-2 py-1" value={schedTime} onChange={(e) => setSchedTime(e.target.value)} />
          <span className="text-xs text-gray-500">(KST)</span>
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          {DAY_LABELS.map((lbl, d) => (
            <button key={d} type="button" onClick={() => toggleDay(d)}
              className={`px-2 py-1 rounded text-sm border ${schedDays.includes(d) ? "bg-blue-600 text-white" : "bg-gray-100"}`}>{lbl}</button>
          ))}
        </div>
        <label className="flex gap-2 items-center text-sm">
          <input type="checkbox" checked={schedEnabled} onChange={(e) => setSchedEnabled(e.target.checked)} />
          스케줄 활성화
        </label>
        <div className="flex gap-2 items-center">
          <button onClick={saveSched} className="px-3 py-1 rounded bg-blue-600 text-white">저장</button>
          <button onClick={deleteSched} className="px-3 py-1 rounded bg-gray-500 text-white">삭제</button>
          {schedMsg && <span className="text-sm text-gray-600">{schedMsg}</span>}
        </div>
      </div>

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
    </div>
  );
}
