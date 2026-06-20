import { BrowserRouter, Routes, Route } from "react-router-dom";
import AppShell from "./components/AppShell";
import Dashboard from "./pages/Dashboard";
import Holdings from "./pages/Holdings";
import Watchlist from "./pages/Watchlist";
import AssetDetail from "./pages/AssetDetail";
import Settings from "./pages/Settings";

// 임시 스텁 — Task 10에서 실제 페이지로 교체
const Alerts = () => <div className="p-6">알림 페이지 준비 중…</div>;

export default function App() {
  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/manage" element={<Holdings />} />
          <Route path="/asset/:id" element={<AssetDetail />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}
