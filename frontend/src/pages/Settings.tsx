import { useEffect, useState } from "react";
import { api } from "../api";

const DAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"];

function MarketSummaryBlock({ market, label }: { market: string; label: string }) {
  const [time, setTime] = useState("08:30");
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [enabled, setEnabled] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.getMarketSummarySchedule(market).then((s) => {
      if (s) { setTime(s.send_time); setDays(s.days_of_week); setEnabled(s.enabled); }
    }).catch(() => {});
  }, [market]);

  const toggle = (d: number) =>
    setDays((p) => p.includes(d) ? p.filter((x) => x !== d) : [...p, d].sort());
  const save = async () => {
    setMsg("저장 중…");
    try { await api.saveMarketSummarySchedule(market, { send_time: time, days_of_week: days, enabled }); setMsg("저장됨"); }
    catch (e: any) { setMsg("저장 실패: " + e.message); }
  };
  const remove = async () => {
    setMsg("삭제 중…");
    try { await api.deleteMarketSummarySchedule(market); setEnabled(false); setMsg("삭제됨"); }
    catch (e: any) { setMsg("삭제 실패: " + e.message); }
  };
  const sendNow = async () => {
    setMsg("발송 중…");
    try { const r = await api.sendMarketSummary(market); setMsg(r.sent ? `발송 완료(지수 ${r.indices}·보유 ${r.holdings}·관심 ${r.watchlist})` : "발송 실패"); }
    catch (e: any) { setMsg("발송 실패: " + e.message); }
  };

  return (
    <div className="border rounded p-3 space-y-2">
      <div className="font-medium">{label}</div>
      <div className="flex items-center gap-2 flex-wrap">
        <label className="text-sm">시각</label>
        <input type="time" className="border rounded px-2 py-1" value={time} onChange={(e) => setTime(e.target.value)} />
        <span className="text-xs text-gray-500">(KST)</span>
      </div>
      <div className="flex items-center gap-1 flex-wrap">
        {DAY_LABELS.map((lbl, d) => (
          <button key={d} type="button" onClick={() => toggle(d)}
            className={`px-2 py-1 rounded text-sm border ${days.includes(d) ? "bg-blue-600 text-white" : "bg-gray-100"}`}>{lbl}</button>
        ))}
      </div>
      <label className="flex gap-2 items-center text-sm">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        활성화
      </label>
      <div className="flex gap-2 items-center">
        <button onClick={save} className="px-3 py-1 rounded bg-blue-600 text-white">저장</button>
        <button onClick={remove} className="px-3 py-1 rounded bg-gray-500 text-white">삭제</button>
        <button onClick={sendNow} className="px-3 py-1 rounded bg-emerald-600 text-white">지금 발송</button>
        {msg && <span className="text-sm text-gray-600">{msg}</span>}
      </div>
    </div>
  );
}

export default function Settings() {
  // 텔레그램
  const [chatId, setChatId] = useState("");
  const [token, setToken] = useState("");
  const [tokenSet, setTokenSet] = useState(false);
  const [tgMsg, setTgMsg] = useState("");

  // AI
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiKeySet, setApiKeySet] = useState(false);
  const [model, setModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [prompt, setPrompt] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [aiMsg, setAiMsg] = useState("");

  const load = async () => {
    const t = await api.getTelegram();
    setChatId(t.chat_id); setTokenSet(t.bot_token_set); setToken("");
    const a = await api.getAi();
    setBaseUrl(a.base_url); setApiKeySet(a.api_key_set); setApiKey("");
    setModel(a.model); setPrompt(a.prompt); setEnabled(a.enabled);
  };
  useEffect(() => { load(); }, []);

  const saveTg = async () => {
    setTgMsg("저장 중…");
    const payload: any = { chat_id: chatId };
    if (token) payload.bot_token = token;
    await api.saveTelegram(payload);
    setTgMsg("저장됨"); await load();
  };

  const saveAi = async () => {
    setAiMsg("저장 중…");
    const payload: any = { base_url: baseUrl, model, prompt, enabled };
    if (apiKey) payload.api_key = apiKey;
    await api.saveAi(payload);
    setAiMsg("저장됨"); await load();
  };

  const refreshModels = async () => {
    setAiMsg("모델 조회 중…");
    try {
      const r = await api.listAiModels();
      setModels(r.models);
      if (!model && r.models.length > 0) setModel(r.models[0]);
      setAiMsg(r.error ? `조회 실패: ${r.error}` : `${r.models.length}개 모델`);
    } catch (e: any) { setAiMsg("조회 실패: " + e.message); }
  };

  return (
    <div className="p-6 space-y-6 max-w-xl">
      <h1 className="text-xl font-bold">설정</h1>

      <section className="space-y-2">
        <h2 className="font-semibold text-gray-700">텔레그램</h2>
        <div className="flex gap-2 items-center">
          <label className="w-28 text-sm">봇 토큰</label>
          <input className="border rounded px-2 py-1 flex-1" type="password"
            placeholder={tokenSet ? "설정됨 (변경 시에만 입력)" : "봇 토큰 입력"}
            value={token} onChange={(e) => setToken(e.target.value)} />
        </div>
        <div className="flex gap-2 items-center">
          <label className="w-28 text-sm">chat_id</label>
          <input className="border rounded px-2 py-1 flex-1" placeholder="chat_id"
            value={chatId} onChange={(e) => setChatId(e.target.value)} />
        </div>
        <button onClick={saveTg} className="px-3 py-1 rounded bg-blue-600 text-white">저장</button>
        {tgMsg && <span className="text-sm text-gray-600 ml-2">{tgMsg}</span>}
      </section>

      <section className="space-y-2">
        <h2 className="font-semibold text-gray-700">AI 분석</h2>
        <div className="flex gap-2 items-center">
          <label className="w-28 text-sm">게이트웨이 URL</label>
          <input className="border rounded px-2 py-1 flex-1" placeholder="http://gateway:4000"
            value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
        </div>
        <div className="flex gap-2 items-center">
          <label className="w-28 text-sm">API 키</label>
          <input className="border rounded px-2 py-1 flex-1" type="password"
            placeholder={apiKeySet ? "설정됨 (변경 시에만 입력)" : "API 키 입력"}
            value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        </div>
        <div className="flex gap-2 items-center">
          <label className="w-28 text-sm">모델</label>
          {models.length > 0 ? (
            <select className="border rounded px-2 py-1 flex-1" value={model}
              onChange={(e) => setModel(e.target.value)}>
              {!models.includes(model) && model && <option value={model}>{model}</option>}
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          ) : (
            <input className="border rounded px-2 py-1 flex-1" placeholder="gemini/gemini-2.5-flash"
              value={model} onChange={(e) => setModel(e.target.value)} />
          )}
          <button onClick={refreshModels} className="px-2 py-1 rounded bg-gray-700 text-white text-sm whitespace-nowrap">모델 새로고침</button>
        </div>
        <div>
          <label className="text-sm block mb-1">프롬프트 (비우면 기본 프롬프트 사용)</label>
          <textarea className="border rounded px-2 py-1 w-full h-40 text-sm font-mono"
            value={prompt} onChange={(e) => setPrompt(e.target.value)} />
        </div>
        <label className="flex gap-2 items-center text-sm">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          AI 분석 사용 (텔레그램 발송 시 분석 코멘트 동반)
        </label>
        <button onClick={saveAi} className="px-3 py-1 rounded bg-blue-600 text-white">저장</button>
        {aiMsg && <span className="text-sm text-gray-600 ml-2">{aiMsg}</span>}
      </section>

      <section className="space-y-2">
        <h2 className="font-semibold text-gray-700">증시 마감 요약</h2>
        <MarketSummaryBlock market="US" label="미국 증시 (US)" />
        <MarketSummaryBlock market="KR" label="한국 증시 (KR)" />
      </section>
    </div>
  );
}
