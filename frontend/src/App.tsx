import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Holdings from "./pages/Holdings";
import Charts from "./pages/Charts";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <BrowserRouter>
      <nav className="flex gap-4 border-b px-6 py-3">
        <Link to="/" className="font-semibold">대시보드</Link>
        <Link to="/holdings">보유</Link>
        <Link to="/charts">차트</Link>
        <Link to="/settings">설정</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/holdings" element={<Holdings />} />
        <Route path="/charts" element={<Charts />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </BrowserRouter>
  );
}
