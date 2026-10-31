import type { ButtonHTMLAttributes, ReactNode } from "react";
import { AlertTriangle, Inbox } from "lucide-react";
import { cn } from "@/lib/format";
import type { Tier } from "@/api/client";

export function Card({ className, children, title, actions }: {
  className?: string;
  children: ReactNode;
  title?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className={cn("rounded-lg border border-line bg-panel", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted">{title}</h2>
          {actions}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

const TIER_STYLE: Record<Tier, string> = {
  HIGH: "bg-sev-high/15 text-sev-high ring-sev-high/40",
  MEDIUM: "bg-sev-medium/15 text-sev-medium ring-sev-medium/40",
  LOW: "bg-sev-low/20 text-slate-300 ring-sev-low/50",
};

export function TierBadge({ tier }: { tier: Tier }) {
  return (
    <span className={cn("inline-flex rounded px-1.5 py-0.5 text-[11px] font-semibold ring-1", TIER_STYLE[tier])}>
      {tier}
    </span>
  );
}

export function Badge({ children, tone = "slate", className }: {
  children: ReactNode;
  tone?: "slate" | "blue" | "green" | "amber" | "red" | "violet";
  className?: string;
}) {
  const tones = {
    slate: "bg-slate-700/40 text-slate-300",
    blue: "bg-sky-500/15 text-sky-300",
    green: "bg-emerald-500/15 text-emerald-300",
    amber: "bg-amber-500/15 text-amber-300",
    red: "bg-red-500/15 text-red-300",
    violet: "bg-violet-500/15 text-violet-300",
  };
  return <span className={cn("inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px]", tones[tone], className)}>{children}</span>;
}

export function Button({ className, variant = "default", ...p }: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "primary" | "ghost";
}) {
  const v = {
    default: "border border-line bg-panel2 hover:bg-slate-700/60",
    primary: "bg-sky-600 text-white hover:bg-sky-500",
    ghost: "hover:bg-slate-700/50",
  };
  return (
    <button
      {...p}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition disabled:cursor-not-allowed disabled:opacity-50",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400",
        v[variant],
        className,
      )}
    />
  );
}

export const Skeleton = ({ className }: { className?: string }) => (
  <div className={cn("animate-pulse rounded bg-slate-700/40", className)} aria-hidden="true" />
);

export function SkeletonRows({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-2" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-8 w-full" />)}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center text-muted">
      <Inbox className="h-6 w-6" aria-hidden="true" />
      <p className="text-sm font-medium text-slate-300">{title}</p>
      {children && <div className="max-w-md text-xs">{children}</div>}
    </div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="flex items-start gap-2 rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div>
        <p className="font-medium">Could not load from the TRACE API</p>
        <p className="text-xs text-red-300/80">{msg}</p>
      </div>
    </div>
  );
}

export function Bar({ value, tone = "sky", label }: { value: number; tone?: "sky" | "amber" | "red" | "emerald"; label?: string }) {
  const tones = { sky: "bg-sky-500", amber: "bg-amber-500", red: "bg-red-500", emerald: "bg-emerald-500" };
  return (
    <div className="h-1.5 w-full rounded bg-slate-700/50" role="meter" aria-valuenow={Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className={cn("h-1.5 rounded", tones[tone])} style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
    </div>
  );
}

export function Kpi({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded-lg border border-line bg-panel px-4 py-3">
      <p className="text-[11px] uppercase tracking-wider text-muted">{label}</p>
      <p className="mt-1 font-mono text-2xl font-semibold text-slate-100">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-muted">{hint}</p>}
    </div>
  );
}
