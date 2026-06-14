import { useEffect, useState } from "react";
import { api } from "../api";

export default function Settings() {
  const [chatId, setChatId] = useState("");
  const [token, setToken] = useState("");
  const [tokenSet, setTokenSet] = useState(false);
  const [msg, setMsg] = useState("");

  const load = async () => {
    const t = await api.getTelegram();
    setChatId(t.chat_id); setTokenSet(t.bot_token_set); setToken("");
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    setMsg("저장 중…");
    const payload: any = { chat_id: chatId };
    if (token) payload.bot_token = token;
    await api.saveTelegram(payload);
    setMsg("저장됨"); await load();
  };

  return (
    <div className="p-6 space-y-4 max-w-xl">
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
        <button onClick={save} className="px-3 py-1 rounded bg-blue-600 text-white">저장</button>
        {msg && <span className="text-sm text-gray-600 ml-2">{msg}</span>}
      </section>
    </div>
  );
}
