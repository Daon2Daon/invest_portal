import { useEffect, useState } from "react";
import { api } from "../api";

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
    </div>
  );
}
