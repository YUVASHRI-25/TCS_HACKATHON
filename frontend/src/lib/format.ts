import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export const cn = (...v: ClassValue[]) => twMerge(clsx(v));

const nf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

export const num = (v: number | null | undefined) => (v === null || v === undefined ? "–" : nf.format(v));
export const short = (v: number | null | undefined) => (v === null || v === undefined ? "–" : compact.format(v));
export const pct = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined ? "–" : `${(v * 100).toFixed(digits)}%`;

export const ts = (v: string | null | undefined) => {
  if (!v) return "–";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? v : d.toISOString().replace("T", " ").slice(0, 16) + " UTC";
};

const ACRONYMS: Record<string, string> = { ip: "IP", kyc: "KYC", ml: "ML", nat: "NAT" };

export const humanize = (s: string) =>
  s
    .toLowerCase()
    .split("_")
    .map((w) => ACRONYMS[w] ?? w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");

/** Money totals per currency. TRACE never converts between currencies (no FX rates in the data). */
export const byCurrency = (m: Record<string, unknown> | undefined) =>
  Object.entries((m ?? {}) as Record<string, number>)
    .sort((a, b) => b[1] - a[1])
    .map(([c, v]) => `${short(v)} ${c}`)
    .join(" · ");
