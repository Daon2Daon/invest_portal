import { useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { currentTheme, setTheme, type Theme } from "../theme";

const NAV = [
  { to: "/", label: "포트폴리오", end: true },
  { to: "/watchlist", label: "관심종목" },
  { to: "/alerts", label: "알림" },
  { to: "/manage", label: "관리" },
  { to: "/settings", label: "설정" },
];

function ThemeToggle() {
  const [t, setT] = useState<Theme>(currentTheme());
  const flip = () => { const n = t === "dark" ? "light" : "dark"; setTheme(n); setT(n); };
  return (
    <button onClick={flip} className="btn btn-ghost text-sm" title="테마 전환">
      {t === "dark" ? "☀️ 라이트" : "🌙 다크"}
    </button>
  );
}

function links(onClick?: () => void) {
  return NAV.map((n) => (
    <NavLink
      key={n.to}
      to={n.to}
      end={n.end}
      onClick={onClick}
      className={({ isActive }) =>
        `block rounded-lg px-3 py-2 text-sm ${isActive ? "bg-surface-2 text-accent font-semibold" : "text-muted hover:text-text"}`
      }
    >
      {n.label}
    </NavLink>
  ));
}

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen lg:flex">
      {/* 좁은 화면: 상단 탭바 */}
      <header className="lg:hidden border-b border-border bg-surface">
        <div className="flex items-center justify-between px-4 py-3">
          <span className="font-extrabold">invest</span>
          <ThemeToggle />
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2">{links()}</nav>
      </header>

      {/* 넓은 화면: 좌측 사이드바 */}
      <aside className="hidden lg:flex lg:w-56 lg:flex-col lg:border-r lg:border-border lg:bg-surface lg:p-4">
        <div className="mb-6 flex items-center justify-between">
          <span className="font-extrabold">💰 invest</span>
        </div>
        <nav className="flex-1 space-y-1">{links()}</nav>
        <div className="pt-4"><ThemeToggle /></div>
      </aside>

      <main className="flex-1">{children}</main>
    </div>
  );
}
