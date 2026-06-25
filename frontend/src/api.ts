// 세션 만료 등으로 임의 API가 401을 반환할 때 호출되는 전역 핸들러(AuthProvider가 등록).
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

// 빈 문자열 = 같은 오리진. 프로덕션(Docker)에선 FastAPI가 SPA·API를 함께 서빙하고,
// dev에선 Vite 프록시(/api → :8000)가 처리한다.
const BASE = "";
export const ASSET_CLASSES = ["주식", "채권", "현금성", "원자재", "가상자산", "대체투자", "기타"];

async function j<T>(p: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + p, {
    headers: { "Content-Type": "application/json" }, ...init,
  });
  // /api/auth/ 호출(로그인 시도 등)의 401은 전역 핸들러로 넘기지 않는다.
  if (r.status === 401 && !p.startsWith("/api/auth/")) onUnauthorized?.();
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  if (r.status === 204) return undefined as T;
  return r.json();
}

export interface MeResponse {
  auth_enabled: boolean;
  authenticated: boolean;
  username: string | null;
}

export const authApi = {
  me: () => j<MeResponse>("/api/auth/me"),
  login: (username: string, password: string) =>
    j<{ username: string }>("/api/auth/login", {
      method: "POST", body: JSON.stringify({ username, password }),
    }),
  logout: () => j<void>("/api/auth/logout", { method: "POST" }),
};

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
  getAi: () => j<{ base_url: string; api_key_set: boolean; model: string; prompt: string; enabled: boolean }>("/api/settings/ai"),
  saveAi: (a: { base_url?: string; api_key?: string; model?: string; prompt?: string; enabled?: boolean }) =>
    j("/api/settings/ai", { method: "PUT", body: JSON.stringify(a) }),
  listAiModels: () => j<{ models: string[]; error?: string }>("/api/settings/ai/models"),
  analyzeChart: (id: number) => j<{ analysis: string }>(`/api/charts/${id}/analyze`, { method: "POST" }),
  getSchedule: (id: number) =>
    j<{ send_time: string; days_of_week: number[]; enabled: boolean } | null>(`/api/charts/${id}/schedule`),
  saveSchedule: (id: number, s: { send_time: string; days_of_week: number[]; enabled: boolean }) =>
    j(`/api/charts/${id}/schedule`, { method: "PUT", body: JSON.stringify(s) }),
  deleteSchedule: (id: number) =>
    j(`/api/charts/${id}/schedule`, { method: "DELETE" }),
  listWatchlist: () => j<WatchlistItem[]>("/api/watchlist"),
  createWatchlistAsset: (a: any) => j("/api/assets", { method: "POST", body: JSON.stringify(a) }),
  assetDetail: (id: number) => j<AssetDetailOut>(`/api/assets/${id}/detail`),
  deleteAsset: (id: number) => j(`/api/assets/${id}`, { method: "DELETE" }),
  listAlerts: (assetId: number) => j<AlertView[]>(`/api/alerts?asset_id=${assetId}`),
  listAllAlerts: () => j<AlertRow[]>("/api/alerts"),
  getTrend: (period: string) => j<TrendPoint[]>(`/api/trend?period=${period}`),
  updateAlert: (id: number, a: { value?: number; direction?: AlertDirection; enabled?: boolean }) =>
    j(`/api/alerts/${id}`, { method: "PUT", body: JSON.stringify(a) }),
  createAlert: (a: AlertCreate) => j("/api/alerts", { method: "POST", body: JSON.stringify(a) }),
  rearmAlert: (id: number) => j(`/api/alerts/${id}/rearm`, { method: "POST" }),
  deleteAlert: (id: number) => j(`/api/alerts/${id}`, { method: "DELETE" }),
  listReports: () => j<ReportRow[]>("/api/reports"),
  getReport: (id: number) => j<ReportRow>(`/api/reports/${id}`),
  createReport: () => j<ReportRow>("/api/reports", { method: "POST" }),
  deleteReport: (id: number) => j(`/api/reports/${id}`, { method: "DELETE" }),
  sendReportTelegram: (id: number) => j<{ sent: number }>(`/api/reports/${id}/send-telegram`, { method: "POST" }),
  getAiReport: () => j<{ model: string; prompt: string; enabled: boolean }>("/api/settings/ai-report"),
  saveAiReport: (a: { model?: string; prompt?: string; enabled?: boolean }) =>
    j("/api/settings/ai-report", { method: "PUT", body: JSON.stringify(a) }),
  getReportSchedule: () =>
    j<{ send_time: string; days_of_week: number[]; enabled: boolean } | null>("/api/reports/schedule"),
  saveReportSchedule: (s: { send_time: string; days_of_week: number[]; enabled: boolean }) =>
    j("/api/reports/schedule", { method: "PUT", body: JSON.stringify(s) }),
  getMarketSummarySchedule: (m: string) =>
    j<{ send_time: string; days_of_week: number[]; enabled: boolean } | null>(`/api/market-summary/${m}/schedule`),
  saveMarketSummarySchedule: (m: string, s: { send_time: string; days_of_week: number[]; enabled: boolean }) =>
    j(`/api/market-summary/${m}/schedule`, { method: "PUT", body: JSON.stringify(s) }),
  deleteMarketSummarySchedule: (m: string) =>
    j(`/api/market-summary/${m}/schedule`, { method: "DELETE" }),
  sendMarketSummary: (m: string) =>
    j<{ market: string; sent: boolean; indices: number; holdings: number; watchlist: number }>(`/api/market-summary/${m}/send`, { method: "POST" }),
  getRiskSignal: () => j<{
    enabled: boolean; sig_rsi: boolean; sig_macd: boolean; sig_bollinger: boolean; sig_ma: boolean;
    sig_concentration_asset: boolean; sig_concentration_class: boolean;
    threshold_asset_pct: number; threshold_class_pct: number;
  }>("/api/risk-signal/settings"),
  saveRiskSignal: (s: Record<string, boolean | number>) =>
    j("/api/risk-signal/settings", { method: "PUT", body: JSON.stringify(s) }),
  getRiskSchedule: () =>
    j<{ send_time: string; days_of_week: number[]; enabled: boolean } | null>("/api/risk-signal/schedule"),
  saveRiskSchedule: (s: { send_time: string; days_of_week: number[]; enabled: boolean }) =>
    j("/api/risk-signal/schedule", { method: "PUT", body: JSON.stringify(s) }),
  previewRiskSignal: () => j<{ text: string }>("/api/risk-signal/preview", { method: "POST" }),
  sendRiskSignal: () => j<{ sent: boolean }>("/api/risk-signal/send", { method: "POST" }),
  listJournal: (assetId?: number) =>
    j<JournalEntry[]>(`/api/journal${assetId != null ? `?asset_id=${assetId}` : ""}`),
  getJournal: (id: number) => j<JournalEntry>(`/api/journal/${id}`),
  createJournal: (e: { title: string; body?: string; asset_id?: number | null; entry_date?: string }) =>
    j<JournalEntry>("/api/journal", { method: "POST", body: JSON.stringify(e) }),
  updateJournal: (id: number, e: { title?: string; body?: string; asset_id?: number | null; entry_date?: string }) =>
    j<JournalEntry>(`/api/journal/${id}`, { method: "PUT", body: JSON.stringify(e) }),
  deleteJournal: (id: number) => j(`/api/journal/${id}`, { method: "DELETE" }),
};

export type ReportRow = {
  id: number; title: string; content_md: string;
  model: string; trigger: string; created_at: string | null;
};
export interface TrendPoint {
  date: string;
  total_value_krw: number;
  total_cost_krw: number;
  total_pl_krw: number;
  total_cash_krw: number;
  allocation: { asset_class: string; value_krw: number }[];
}
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
export interface WatchlistItem {
  asset_id: number; ticker: string; name: string; market: string; currency: string;
  asset_type: string; asset_class: string | null;
  current_price: number | null; change: number | null; change_pct: number | null;
  price_status: string;
}
export interface HoldingSummary {
  quantity: number; avg_price: number; value_krw: number;
  profit_loss_krw: number; profit_loss_pct: number;
}
export interface AssetDetailOut {
  asset: {
    asset_id: number; ticker: string; name: string; market: string; currency: string;
    asset_type: string; asset_class: string | null; data_source: string;
  };
  held: boolean;
  holding_summary: HoldingSummary | null;
  quote: { price: number; currency: string; change: number | null; change_pct: number | null; status: string };
}
export type AlertBasis = "ABSOLUTE" | "PURCHASE_AVG" | "WEEK52_HIGH" | "WEEK52_LOW" | "REFERENCE";
export type AlertDirection = "ABOVE" | "BELOW" | "BOTH";
export interface AlertCreate {
  asset_id: number; basis: AlertBasis; direction: AlertDirection; value: number; note?: string | null;
}
export interface AlertView {
  alert_id: number; asset_id: number; basis: AlertBasis; direction: AlertDirection;
  value: number; enabled: boolean; is_triggered: boolean; note: string | null;
  target_price: number | null; reference_price: number | null;
  current_price: number | null; price_status: string; fired: boolean;
}
export interface AlertRow extends AlertView {
  asset_name: string; ticker: string; market: string; asset_class: string | null;
}
export type JournalEntry = {
  id: number; entry_date: string; title: string; body: string | null;
  asset_id: number | null; asset_name: string | null; asset_ticker: string | null;
  created_at: string | null; updated_at: string | null;
};
