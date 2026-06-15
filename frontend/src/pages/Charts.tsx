import { useEffect, useState } from "react";
import { api } from "../api";

export default function Charts() {
  const [assets, setAssets] = useState<any[]>([]);
  const [assetId, setAssetId] = useState<number | null>(null);
  const [nonce, setNonce] = useState(() => Date.now());  // 이미지 캐시 버스트(로드마다 고유)
  const [msg, setMsg] = useState("");

  useEffect(() => { api.listAssets().then((a) => { setAssets(a); if (a[0]) setAssetId(a[0].asset_id); }); }, []);

  const send = async () => {
    if (!assetId) return;
    setMsg("발송 중…");
    try {
      const r: any = await api.sendChartTelegram(assetId);
      setMsg(r.ok ? `텔레그램 발송 완료 (${r.sent}장)` : "발송 실패");
    } catch (e: any) { setMsg("발송 실패: " + e.message); }
  };

  const src = (period: "daily" | "weekly") =>
    assetId ? `${api.chartUrl(assetId, period)}&n=${nonce}` : "";

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <h1 className="text-xl font-bold">차트</h1>
        <select className="border rounded px-2 py-1" value={assetId ?? ""}
          onChange={(e) => { setAssetId(Number(e.target.value)); setMsg(""); }}>
          {assets.map((a) => <option key={a.asset_id} value={a.asset_id}>{a.name} ({a.ticker}·{a.market})</option>)}
        </select>
        <button onClick={() => setNonce((n) => n + 1)} className="px-3 py-1 rounded bg-gray-800 text-white">새로고침</button>
        <button onClick={send} className="px-3 py-1 rounded bg-blue-600 text-white">텔레그램 발송</button>
        {msg && <span className="text-sm text-gray-600">{msg}</span>}
      </div>
      {assetId && (
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
      )}
    </div>
  );
}
