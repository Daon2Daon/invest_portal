// 라이트/다크 테마: 저장값 우선, 없으면 시스템 설정. <html data-theme>에 적용.
export type Theme = "light" | "dark";

const KEY = "theme";

export function resolveInitialTheme(): Theme {
  const saved = localStorage.getItem(KEY);
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(t: Theme) {
  document.documentElement.setAttribute("data-theme", t);
}

export function setTheme(t: Theme) {
  localStorage.setItem(KEY, t);
  applyTheme(t);
}

export function currentTheme(): Theme {
  return (document.documentElement.getAttribute("data-theme") as Theme) || "light";
}
