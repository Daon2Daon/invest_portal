import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Holdings from "./pages/Holdings";
import Watchlist from "./pages/Watchlist";
import AssetDetail from "./pages/AssetDetail";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <BrowserRouter>
      <nav className="flex gap-4 border-b px-6 py-3">
        <Link to="/" className="font-semibold">포트폴리오</Link>
        <Link to="/watchlist">관심종목</Link>
        <Link to="/manage">관리</Link>
        <Link to="/settings">설정</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/watchlist" element={<Watchlist />} />
        <Route path="/manage" element={<Holdings />} />
        <Route path="/asset/:id" element={<AssetDetail />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </BrowserRouter>
  );
}
