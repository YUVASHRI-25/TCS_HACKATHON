import { X } from "lucide-react";
import { useUi } from "@/store/ui";
import { useEvidence } from "@/hooks/useApi";
import { Badge, ErrorState, SkeletonRows } from "@/components/ui/primitives";
import { humanize, ts } from "@/lib/format";

function RowsTable({ rows }: { rows: Record<string, unknown>[] }) {
  const cols = Array.from(new Set(rows.flatMap((r) => Object.keys(r))));
  return (
    <div className="overflow-auto rounded border border-line">
      <table className="w-full text-left font-mono text-[11px]">
        <thead className="bg-panel2 text-muted">
          <tr>{cols.map((c) => <th key={c} className="whitespace-nowrap px-2 py-1.5 font-medium">{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line">
              {cols.map((c) => <td key={c} className="whitespace-nowrap px-2 py-1">{r[c] === null || r[c] === undefined ? "–" : String(r[c])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Evidence drawer: description, the raw source rows it resolves to, and the equivalent Cypher. */
export function EvidenceDrawer() {
  const ev = useUi((s) => s.evidence);
  const close = useUi((s) => s.closeEvidence);
  const q = useEvidence(ev?.caseId ?? "", ev?.eid ?? null);
  if (!ev) return null;
  const d = q.data;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/40" onClick={close}>
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`Evidence ${ev.eid}`}
        className="flex h-full w-full max-w-3xl flex-col border-l border-line bg-panel shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === "Escape" && close()}
      >
        <header className="flex items-center justify-between border-b border-line px-5 py-3">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm text-sky-300">{ev.eid}</span>
            {d && <Badge tone={d.source === "model" ? "violet" : "blue"}>{d.source}</Badge>}
            {d && <span className="text-sm font-medium">{humanize(d.finding_type)}</span>}
          </div>
          <button type="button" onClick={close} aria-label="Close evidence" className="rounded p-1 hover:bg-slate-700/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400">
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="flex-1 space-y-5 overflow-auto p-5">
          {q.isLoading && <SkeletonRows rows={8} />}
          {q.isError && <ErrorState error={q.error} />}
          {d && (
            <>
              <p className="text-sm leading-relaxed">{d.description}</p>
              <dl className="grid grid-cols-3 gap-3 text-xs">
                <div><dt className="text-muted">Strength</dt><dd className="font-mono">{d.strength.toFixed(3)}</dd></div>
                <div><dt className="text-muted">First seen</dt><dd className="font-mono">{ts(d.ts_min)}</dd></div>
                <div><dt className="text-muted">Last seen</dt><dd className="font-mono">{ts(d.ts_max)}</dd></div>
                <div><dt className="text-muted">Source rows</dt><dd className="font-mono">{d.n_source_rows}</dd></div>
                <div className="col-span-2"><dt className="text-muted">Entities</dt><dd className="font-mono break-all">{d.entities.slice(0, 12).join(", ")}{d.entities.length > 12 ? ` +${d.entities.length - 12}` : ""}</dd></div>
              </dl>
              {d.source === "model" && (
                <p className="rounded border border-violet-500/30 bg-violet-500/10 p-2 text-xs text-violet-200">
                  Model signal: capped at 20 points combined and never sufficient to open a case on its own.
                </p>
              )}
              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Raw source records ({d.raw_rows.length})</h3>
                {d.raw_rows.length ? <RowsTable rows={d.raw_rows} /> : <p className="text-xs text-muted">This evidence item has no row-level source (model signal).</p>}
              </section>
              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Equivalent graph query (Cypher)</h3>
                <pre className="overflow-auto rounded border border-line bg-canvas p-3 font-mono text-[11px] text-emerald-200">{d.cypher_used}</pre>
              </section>
              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Details</h3>
                <pre className="overflow-auto rounded border border-line bg-canvas p-3 font-mono text-[11px]">{JSON.stringify(d.details, null, 2)}</pre>
              </section>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
