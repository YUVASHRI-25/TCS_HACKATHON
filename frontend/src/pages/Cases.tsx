import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowDownUp } from "lucide-react";
import { useCases } from "@/hooks/useApi";
import { Badge, Card, EmptyState, ErrorState, SkeletonRows, TierBadge } from "@/components/ui/primitives";
import { humanize, num, short } from "@/lib/format";
import type { CaseSummary } from "@/api/client";

type SortKey = "priority_score" | "n_members" | "exposure_total";

export function CasesPage() {
  const [params, setParams] = useSearchParams();
  const tier = params.get("tier") ?? "";
  const status = params.get("status") ?? "";
  const q = params.get("q") ?? "";
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "priority_score", desc: true });
  const cases = useCases({ tier, status, q });

  const rows = useMemo(() => {
    const r = [...(cases.data ?? [])];
    r.sort((a, b) => (sort.desc ? b[sort.key] - a[sort.key] : a[sort.key] - b[sort.key]));
    return r;
  }, [cases.data, sort]);

  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p);
  };
  const Th = ({ k, children }: { k: SortKey; children: string }) => (
    <th className="px-3 py-2 text-right font-medium">
      <button type="button" className="inline-flex items-center gap-1 hover:text-slate-200"
        onClick={() => setSort((s) => ({ key: k, desc: s.key === k ? !s.desc : true }))}
        aria-label={`Sort by ${children}`}>
        {children} <ArrowDownUp className="h-3 w-3" aria-hidden="true" />
      </button>
    </th>
  );

  return (
    <div className="space-y-4 p-6">
      <h1 className="text-lg font-semibold">Case queue</h1>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <label className="flex items-center gap-2">
          <span className="text-muted">Tier</span>
          <select value={tier} onChange={(e) => set("tier", e.target.value)} className="rounded border border-line bg-panel px-2 py-1">
            <option value="">All</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option>
          </select>
        </label>
        <label className="flex items-center gap-2">
          <span className="text-muted">Status</span>
          <select value={status} onChange={(e) => set("status", e.target.value)} className="rounded border border-line bg-panel px-2 py-1">
            <option value="">All</option>
            {["open", "under_review", "escalated", "resolved"].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </select>
        </label>
        <input value={q} onChange={(e) => set("q", e.target.value)} placeholder="Filter by id or summary" aria-label="Filter cases"
          className="rounded border border-line bg-panel px-2 py-1" />
        <span className="ml-auto text-xs text-muted">{rows.length} cases</span>
      </div>
      <Card className="overflow-hidden" >
        {cases.isLoading && <SkeletonRows />}
        {cases.isError && <ErrorState error={cases.error} />}
        {cases.data && rows.length === 0 && <EmptyState title="No cases match these filters" />}
        {rows.length > 0 && (
          <div className="-m-4 overflow-auto">
            <table className="w-full text-sm">
              <thead className="bg-panel2 text-left text-xs text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Case</th>
                  <th className="px-3 py-2 font-medium">Tier</th>
                  <Th k="priority_score">Priority</Th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Signals</th>
                  <Th k="n_members">Accounts</Th>
                  <Th k="exposure_total">Exposure</Th>
                </tr>
              </thead>
              <tbody>{rows.map((c: CaseSummary) => (
                <tr key={c.id} className="border-t border-line hover:bg-slate-700/20">
                  <td className="px-3 py-2"><Link to={`/cases/${c.id}`} className="font-mono text-sky-300 hover:underline">{c.id}</Link>
                    {c.origin === "investigator" && <Badge tone="violet" className="ml-1">investigator</Badge>}</td>
                  <td className="px-3 py-2"><TierBadge tier={c.tier} /></td>
                  <td className="tabular px-3 py-2 text-right font-mono">{c.priority_score.toFixed(1)}</td>
                  <td className="px-3 py-2 text-xs">{humanize(c.status)}</td>
                  <td className="px-3 py-2"><div className="flex flex-wrap gap-1">{c.finding_types.map((f) => <Badge key={f} tone={f === "isolation_forest" ? "violet" : "slate"}>{humanize(f)}</Badge>)}</div></td>
                  <td className="tabular px-3 py-2 text-right font-mono">{num(c.n_members)}</td>
                  <td className="tabular px-3 py-2 text-right font-mono">{short(c.exposure_total)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
