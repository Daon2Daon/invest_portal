// 빈 문자열 = 같은 오리진. 프로덕션(Docker)에선 FastAPI가 SPA·API를 함께 서빙하고,
// dev에선 Vite 프록시(/api → :8000)가 처리한다.
const BASE = "";
export const ASSET_CLASSES = ["주식", "채권", "현금성", "원자재", "가상자산", "대체투자", "기타"];

async function j<T>(p: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + p, {
    headers: { "Content-Type": "application/json" }, ...init,
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const api = {
  resolve: (ticker: string, market: string, asset_type?: string) =>
    j<ResolveResponse>("/api/assets/resolve", { method: "POST", body: JSON.stringify({ ticker, market, asset_type }) }),
  listAssets: () => j<any[]>("/api/assets"),
  listHoldings: () => j<any[]>("/api/holdings"),
  updateHolding: (id: number, h: any) =>
    j(`/api/holdings/${id}`, { method: "PUT", body: JSON.stringify(h) }),
  updateAsset: (id: number, a: any) =>
    j(`/api/assets/${id}`, { method: "PUT", body: JSON.stringify(a) }),
  deleteHolding: (id: number) => j(`/api/holdings/${id}`, { method: "DELETE" }),
  portfolio: () => j<PortfolioOut>("/api/portfolio"),
  refresh: () => j<PortfolioOut>("/api/portfolio/refresh", { method: "POST" }),
  createHoldingWithAsset: (h: any) =>
    j("/api/holdings/with-asset", { method: "POST", body: JSON.stringify(h) }),
  listCash: () => j<any[]>("/api/cash"),
  createCash: (c: any) => j("/api/cash", { method: "POST", body: JSON.stringify(c) }),
  updateCash: (id: number, c: any) =>
    j(`/api/cash/${id}`, { method: "PUT", body: JSON.stringify(c) }),
  deleteCash: (id: number) => j(`/api/cash/${id}`, { method: "DELETE" }),
  chartUrl: (id: number, period: "daily" | "weekly") => `/api/charts/${id}?period=${period}`,
  sendChartTelegram: (id: number) => j(`/api/charts/${id}/send-telegram`, { method: "POST" }),
  getTelegram: () => j<{ bot_token_set: boolean; chat_id: string }>("/api/settings/telegram"),
  saveTelegram: (t: { bot_token?: string; chat_id?: string }) =>
    j("/api/settings/telegram", { method: "PUT", body: JSON.stringify(t) }),
};

export interface ResolveResponse {
  ok: boolean;
  asset: any | null;
  tried: string[];
  suggestion: string;
}
export interface Position {
  asset_id: number; ticker: string; name: string; market: string; currency: string;
  asset_class: string;
  quantity: number; avg_price: number; current_price: number;
  cost_native: number; value_native: number; profit_loss_native: number;
  cost_krw: number; value_krw: number; profit_loss_krw: number; profit_loss_pct: number;
  weight_pct: number; price_status: string;
}
export interface CashPosition {
  id: number; currency: string; amount: number; label: string | null;
  value_krw: number; weight_pct: number;
}
export interface AllocationSlice {
  asset_class: string; value_krw: number; weight_pct: number;
}
export interface PortfolioOut {
  positions: Position[];
  cash: CashPosition[];
  allocation: AllocationSlice[];
  summary: { total_value_krw: number; total_cost_krw: number;
             total_profit_loss_krw: number; total_profit_loss_pct: number; total_cash_krw: number };
}
