// 빈 문자열 = 같은 오리진. 프로덕션(Docker)에선 FastAPI가 SPA·API를 함께 서빙하고,
// dev에선 Vite 프록시(/api → :8000)가 처리한다.
const BASE = "";

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
  createAsset: (a: any) => j("/api/assets", { method: "POST", body: JSON.stringify(a) }),
  listAssets: () => j<any[]>("/api/assets"),
  createHolding: (h: any) => j("/api/holdings", { method: "POST", body: JSON.stringify(h) }),
  listHoldings: () => j<any[]>("/api/holdings"),
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
};

export interface ResolveResponse {
  ok: boolean;
  asset: any | null;
  tried: string[];
  suggestion: string;
}
export interface Position {
  asset_id: number; ticker: string; name: string; market: string; currency: string;
  quantity: number; avg_price: number; current_price: number;
  cost_native: number; value_native: number; profit_loss_native: number;
  cost_krw: number; value_krw: number; profit_loss_krw: number; profit_loss_pct: number;
  weight_pct: number; price_status: string;
}
export interface CashPosition {
  id: number; currency: string; amount: number; label: string | null;
  value_krw: number; weight_pct: number;
}
export interface PortfolioOut {
  positions: Position[];
  cash: CashPosition[];
  summary: { total_value_krw: number; total_cost_krw: number;
             total_profit_loss_krw: number; total_profit_loss_pct: number; total_cash_krw: number };
}
