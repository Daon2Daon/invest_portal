import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { AlertRow } from "../api";
import AlertForm, { BASIS_LABEL, type AssetOpt } from "../components/AlertForm";

export default function Alerts() {
  const nav = useNavigate();
  const [rows, setRows] = useState<AlertRow[]>([]);
  const [opts, setOpts] = useState<AssetOpt[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");

  const loadRows = async () => setRows(await api.listAllAlerts());
  const loadOpts = async () => {
    const [pf, wl] = await Promise.all([api.portfolio(), api.listWatchlist()]);
    const held: AssetOpt[] = pf.positions.map((p) => ({
      asset_id: p.asset_id, label: `${p.name} (${p.ticker})`, held: true, manual: false,
    }));
    const heldIds = new Set(held.map((h) => h.asset_id));
    const watch: AssetOpt[] = wl
      .filter((w) => !heldIds.has(w.asset_id))
      .map((w) => ({ asset_id: w.asset_id, label: `${w.name} (${w.ticker})`, held: false, manual: false }));
    setOpts([...held, ...watch]);
  };
  useEffect(() => {
    (async () => { try { await Promise.all([loadRows(), loadOpts()]); } finally { setLoading(false); } })();
  }, []);

  const toggle = async (r: AlertRow) => {
    try { await api.updateAlert(r.alert_id, { enabled: !r.enabled }); await loadRows(); setMsg(""); }
    catch (e: any) { setMsg("작업 실패: " + e.message); }
  };
  const rearm = async (id: number) => {
    try { await api.rearmAlert(id); await loadRows(); setMsg(""); }
    catch (e: any) { setMsg("작업 실패: " + e.message); }
  };
  const del = async (id: number) => {
    try { await api.deleteAlert(id); await loadRows(); setMsg(""); }
    catch (e: any) { setMsg("작업 실패: " + e.message); }
  };

  if (loading) return <div className="p-6">불러오는 중…</div>;
  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-bold">알림</h1>
        {msg && <span className="text-sm text-muted">{msg}</span>}
      </div>
      <div className="card space-y-2">
        <h2 className="font-semibold">알림 추가</h2>
        <AlertForm options={opts} onAdded={loadRows} />
      </div>
      {rows.length === 0 ? (
        <p className="text-muted text-sm">설정된 알림이 없습니다. 위에서 추가하거나 종목 상세에서 설정하세요.</p>
      ) : (
        <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse whitespace-nowrap">
          <thead><tr className="border-b border-border text-left text-muted">
            <th className="py-2">종목</th><th>기준</th><th>방향</th><th>목표가</th><th>현재가</th><th>상태</th><th></th>
          </tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.alert_id} className="border-b border-border hover:bg-surface-2">
                <td className="py-2 cursor-pointer" onClick={() => nav(`/asset/${r.asset_id}`)}>
                  {r.asset_name} <span className="text-muted">{r.ticker}·{r.market}</span>
                </td>
                <td>{BASIS_LABEL[r.basis]}</td>
                <td>{r.direction === "ABOVE" ? "이상" : "이하"}{r.basis === "ABSOLUTE" ? "" : ` ${r.value}%`}</td>
                <td>{r.target_price == null ? "—" : r.target_price.toLocaleString()}</td>
                <td>{r.current_price == null ? "—" : r.current_price.toLocaleString()}</td>
                <td>
                  {r.is_triggered ? <span className="text-muted">발동됨</span>
                    : r.fired ? <span className="badge">도달</span>
                    : r.enabled ? <span className="text-up">활성</span>
                    : <span className="text-muted">꺼짐</span>}
                </td>
                <td className="whitespace-nowrap">
                  {r.is_triggered
                    ? <button onClick={() => rearm(r.alert_id)} className="text-accent mr-2">재무장</button>
                    : <button onClick={() => toggle(r)} className="text-accent mr-2">{r.enabled ? "끄기" : "켜기"}</button>}
                  <button onClick={() => del(r.alert_id)} className="text-up">삭제</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </div>
  );
}
