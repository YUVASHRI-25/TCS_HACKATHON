import { useMetrics } from "@/hooks/useApi";
import { Card, EmptyState, ErrorState, SkeletonRows } from "@/components/ui/primitives";
import { pct } from "@/lib/format";

const fmt = (v: unknown) => (typeof v === "number" ? (v <= 1 && !Number.isInteger(v) ? pct(v) : String(v)) : v === null ? "–" : String(v));

export function MetricsPage() {
  const q = useMetrics();
  if (q.isLoading) return <div className="p-6"><SkeletonRows rows={8} /></div>;
  if (q.isError) return <div className="p-6"><ErrorState error={q.error} /></div>;
  const m = q.data!;
  if (!m.computed) return <div className="p-6"><EmptyState title="Metrics appear after the first pipeline run" /></div>;
  const lab = m.label_report as Record<string, unknown> | null;
  return (
    <div className="space-y-5 p-6">
      <h1 className="text-lg font-semibold">Success measures</h1>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {m.measures.map((x) => (
          <div key={String(x.id)} className="rounded-lg border border-line bg-panel p-4">
            <p className="text-[11px] uppercase tracking-wider text-muted">{String(x.label)}</p>
            <p className="mt-1 font-mono text-2xl">{fmt(x.value)}</p>
            <p className="mt-1 text-xs text-muted">{String(x.note)}</p>
          </div>
        ))}
      </div>
      {lab && (
        <Card title="Ground-truth comparison (report only — labels never tune anything)">
          <dl className="grid gap-x-8 gap-y-2 text-sm md:grid-cols-2">
            {[
              ["Labelled accounts", lab.labelled_positive_accounts],
              ["Base rate (chance precision)", lab.base_rate],
              ["Labelled accounts inside surfaced networks", lab.positive_accounts_in_surfaced_networks],
              ["Share of labelled accounts surfaced", lab.share_of_positive_accounts_surfaced],
              ["Member precision", lab.member_precision],
              ["Lift over base rate", lab.lift_over_base_rate],
              ["Networks with any labelled member", lab.networks_with_any_labelled_member],
              ["…expected by chance for networks of these sizes", lab.networks_with_any_labelled_member_by_chance],
            ].map(([k, v]) => (
              <div key={String(k)} className="flex justify-between border-b border-line py-1"><dt className="text-muted">{String(k)}</dt><dd className="font-mono">{fmt(v)}</dd></div>
            ))}
          </dl>
          <p className="mt-3 text-xs text-muted">Label definition: {String(lab.label_definition)}. Precision@k: {String(lab.precision_at_k_definition)} — {JSON.stringify(lab.precision_at_k)}.</p>
          <p className="mt-2 rounded border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-200">
            A lift near 1.0 means the surfaced networks contain labelled accounts at about the rate a random selection would. This is reported as measured; thresholds were not adjusted toward the labels.
          </p>
        </Card>
      )}
      <Card title="What this does and does not prove">
        <ul className="list-disc space-y-1 pl-5 text-sm">{m.does_not_prove.map((t) => <li key={t}>{t}</li>)}</ul>
      </Card>
    </div>
  );
}
