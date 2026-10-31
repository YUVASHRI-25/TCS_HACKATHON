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
        // Professional white theme: text #172554, accent #2563EB / #6366F1, warning #F59E0B, critical #DC2626, verified #16A34A
        canvas: "#FFFFFF",
        panel: "#FFFFFF",
        panel2: "#F8FAFC",
        line: "#E2E8F0",
        muted: "#64748B",
        sev: { high: "#DC2626", medium: "#F59E0B", low: "#64748B" },
        // Existing components use the dark-theme shade scale; remapped so text is dark-on-white.
        slate: { 100: "#172554", 200: "#172554", 300: "#334155", 400: "#64748B", 500: "#64748B", 600: "#CBD5E1", 700: "#E2E8F0", 800: "#F1F5F9", 900: "#F8FAFC" },
        sky: { 200: "#1E40AF", 300: "#1D4ED8", 400: "#2563EB", 500: "#2563EB", 600: "#2563EB", 700: "#1D4ED8" },
        red: { 200: "#991B1B", 300: "#B91C1C", 400: "#DC2626", 500: "#DC2626" },
        amber: { 200: "#92400E", 300: "#B45309", 400: "#D97706", 500: "#F59E0B" },
        emerald: { 200: "#166534", 300: "#15803D", 400: "#16A34A", 500: "#16A34A" },
        violet: { 200: "#4338CA", 300: "#4F46E5", 400: "#6366F1", 500: "#6366F1" },
      },
    },
  },
  plugins: [],
} satisfies Config;
