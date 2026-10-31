import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      colors: {
        canvas: "#0b1020",
        panel: "#111830",
        panel2: "#172040",
        line: "#24304f",
        muted: "#8b98b8",
        sev: { high: "#ef4444", medium: "#f59e0b", low: "#64748b" },
      },
    },
  },
  plugins: [],
} satisfies Config;
