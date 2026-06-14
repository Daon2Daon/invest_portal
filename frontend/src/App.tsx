import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Assets from "./pages/Assets";
import Holdings from "./pages/Holdings";
import Cash from "./pages/Cash";

export default function App() {
  return (
    <BrowserRouter>
      <nav className="flex gap-4 border-b px-6 py-3">
        <Link to="/" className="font-semibold">대시보드</Link>
        <Link to="/assets">자산</Link>
        <Link to="/holdings">보유</Link>
        <Link to="/cash">현금</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/assets" element={<Assets />} />
        <Route path="/holdings" element={<Holdings />} />
        <Route path="/cash" element={<Cash />} />
      </Routes>
    </BrowserRouter>
  );
}
