import { Link } from "react-router-dom";
import { Bar as RBar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CheckCircle2, MinusCircle, XCircle } from "lucide-react";
import { useDashboard } from "@/hooks/useApi";
import { Badge, Card, EmptyState, ErrorState, Kpi, SkeletonRows, TierBadge } from "@/components/ui/primitives";
import { num, short, ts } from "@/lib/format";
import { VIZ } from "@/lib/viz";
import type { CapabilityOut } from "@/api/client";

function CapabilityRow({ c }: { c: CapabilityOut }) {
  const Icon = !c.enabled ? MinusCircle : c.run_status === "error" ? XCircle : CheckCircle2;
  const tone = !c.enabled ? "text-slate-500" : c.run_status === "error" ? "text-red-400" : "text-emerald-400";
  return (
    <li className="flex items-start gap-2 border-t border-line py-2 first:border-0">
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm">{c.label}</span>
          <Badge>{c.kind}</Badge>
          {!c.deterministic && <Badge tone="violet">model · capped</Badge>}
          <span className="sr-only">{c.enabled ? "enabled" : "disabled"}</span>
          {c.enabled && c.findings !== null && c.findings !== undefined && (
            <span className="ml-auto font-mono text-xs text-muted">{num(c.findings)} findings</span>
          )}
        </div>
        {!c.enabled && <p className="text-xs text-muted">{c.reason}</p>}
        {c.notes.map((n) => <p key={n} className="text-xs text-amber-300/80">{n}</p>)}
      </div>
    </li>
  );
}

export function DashboardPage() {
  const q = useDashboard();
  if (q.isLoading) return <div className="p-6"><SkeletonRows rows={10} /></div>;
  if (q.isError) return <div className="p-6"><ErrorState error={q.error} /></div>;
  const d = q.data!;
  if (!d.pipeline_run)
    return (
      <div className="p-6">
        <EmptyState title="The pipeline has not been run yet">
          Configure <code>config/mapping.yaml</code> and run <code>make pipeline</code>. Nothing is shown until the real data is processed.
        </EmptyState>
      </div>
    );
  const k = d.kpis as Record<string, number | null>;
  return (
    <div className="space-y-5 p-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-lg font-semibold">Investigation overview</h1>
        <p className="text-xs text-muted">Pipeline run {ts(d.run_at)}</p>
      </div>
      <p className="text-xs text-muted">{d.data_statement}</p>
      {d.warnings.map((w) => <p key={w} role="alert" className="rounded border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-200">{w}</p>)}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Kpi label="Networks surfaced" value={num(k.cases)} hint={`${num(k.accounts_in_cases)} accounts`} />
        <Kpi label="Awaiting human review" value={num(k.pending_review)} hint="HIGH tier queue" />
        <Kpi label="Exposure on flagged txns" value={short(k.exposure_surfaced)} hint="summed across currencies — not FX-converted" />
        <Kpi label="Findings" value={num(k.findings)} hint="all detectors" />
        <Kpi label="Transactions processed" value={num(k.transactions_processed)} />
        <Kpi label="Quarantined rows" value={num(k.transactions_quarantined)} hint="logged with reasons" />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card title="Priority score distribution" className="lg:col-span-2">
          <div className="mb-3 flex gap-4 text-xs">
            {(["HIGH", "MEDIUM", "LOW"] as const).map((t) => (
              <Link key={t} to={`/cases?tier=${t}`} className="flex items-center gap-1.5 hover:underline">
                <TierBadge tier={t} /> <span className="font-mono">{d.tiers[t] ?? 0}</span>
              </Link>
            ))}
            <span className="ml-auto text-muted">Priority score, not a probability of wrongdoing</span>
          </div>
          <div className="h-56" role="img" aria-label="Histogram of case priority scores">
            <ResponsiveContainer>
              <BarChart data={d.score_histogram} margin={{ top: 4, right: 8, bottom: 0, left: -20 }} barCategoryGap={2}>
                <CartesianGrid vertical={false} stroke={VIZ.neutral} strokeOpacity={0.35} />
                <XAxis dataKey="bin" tick={{ fill: VIZ.muted, fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis allowDecimals={false} tick={{ fill: VIZ.muted, fontSize: 11 }} tickLine={false} axisLine={false} />
                <Tooltip cursor={{ fill: "#ffffff10" }} contentStyle={{ background: VIZ.surface, border: "1px solid #24304f", fontSize: 12 }}
                  formatter={(v: number) => [v, "cases"]} labelFormatter={(l) => `score ${l}`} />
                <RBar dataKey="count" fill={VIZ.primary} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <details className="mt-2 text-xs text-muted">
            <summary className="cursor-pointer">Table view</summary>
            <table className="mt-1 font-mono">
              <tbody>{d.score_histogram.map((b) => <tr key={String(b.bin)}><td className="pr-4">{String(b.bin)}</td><td>{String(b.count)}</td></tr>)}</tbody>
            </table>
          </details>
        </Card>
        <Card title="Network grouping">
          {d.grouping ? (
            <dl className="space-y-2 text-sm">
              {Object.entries(d.grouping as Record<string, number>).map(([key, v]) => (
                <div key={key} className="flex justify-between"><dt className="text-muted">{key.replace(/_/g, " ")}</dt><dd className="font-mono">{v}</dd></div>
              ))}
            </dl>
          ) : <EmptyState title="No grouping report" />}
          <p className="mt-3 text-xs text-muted">A network becomes a case only with at least two independent deterministic signal types. Model signals never open a case alone.</p>
        </Card>
      </div>

      <Card title="Detector capabilities on this dataset">
        <ul className="grid gap-x-8 md:grid-cols-2">{d.capabilities.map((c) => <CapabilityRow key={c.id} c={c} />)}</ul>
      </Card>
    </div>
  );
}
