export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        border: "var(--border)",
        text: "var(--text)",
        muted: "var(--text-muted)",
        accent: "var(--accent)",
        "accent-fg": "var(--accent-fg)",
        up: "var(--up)",
        down: "var(--down)",
        "ok-bg": "var(--ok-bg)",
        "ok-text": "var(--ok-text)",
        "warn-bg": "var(--warn-bg)",
        "warn-text": "var(--warn-text)",
      },
    },
  },
  plugins: [],
}
