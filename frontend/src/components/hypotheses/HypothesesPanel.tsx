import type { CaseOut } from "@/api/client";
import { EvidenceChips } from "@/components/evidence/EvidenceChip";
import { Badge, Bar, Card, EmptyState } from "@/components/ui/primitives";
import { humanize, pct } from "@/lib/format";

export function HypothesesPanel({ c }: { c: CaseOut }) {
  return (
    <div className="space-y-4">
      <Card title="Competing hypotheses (fixed typology catalogue)">
        {c.hypotheses.length === 0 ? <EmptyState title="No catalogued typology has its defining signals present" /> : (
          <div className="grid gap-3 xl:grid-cols-2">
            {c.hypotheses.map((h) => (
              <article key={h.id} className="rounded-md border border-line bg-panel2/50 p-3">
                <header className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-medium">{h.label}</h3>
                    <p className="text-xs text-muted">{h.description}</p>
                  </div>
                  <span className="font-mono text-xs">{pct(h.support, 0)}</span>
                </header>
                <div className="my-2"><Bar value={h.support} label={`${h.label} support`} /></div>
                <dl className="space-y-1.5 text-xs">
                  <div><dt className="text-muted">Evidence for</dt><dd><EvidenceChips caseId={c.id} ids={h.evidence_for} /></dd></div>
                  <div><dt className="text-muted">Evidence against (legitimate explanations with fit)</dt><dd><EvidenceChips caseId={c.id} ids={h.evidence_against} /></dd></div>
                  <div><dt className="text-muted">Supporting signals not observed</dt><dd>{h.missing_signals.length ? h.missing_signals.map(humanize).join(", ") : "–"}</dd></div>
                </dl>
              </article>
            ))}
          </div>
        )}
        <p className="mt-3 text-xs text-muted">Support = weighted share of the typology's supporting signals that are present. It is not a likelihood of wrongdoing.</p>
      </Card>
      <Card title="Legitimate explanations considered">
        <ul className="space-y-3">
          {c.alternatives.map((a) => (
            <li key={a.id} className="grid grid-cols-[14rem_1fr] gap-3 text-xs">
              <div>
                <p className="text-sm">{a.label}</p>
                {a.status === "evaluated" && <Badge tone="green">evaluated</Badge>}
                {a.status === "cannot_evaluate" && <Badge tone="amber">cannot evaluate</Badge>}
                {a.status === "not_applicable" && <Badge>not applicable</Badge>}
              </div>
              <div className="space-y-1">
                {a.status === "evaluated" && a.fit !== null && (
                  <div className="flex items-center gap-2"><div className="w-48"><Bar value={a.fit} tone="amber" label={`${a.label} fit`} /></div><span className="font-mono">fit {a.fit.toFixed(2)}</span></div>
                )}
                <p className="text-slate-300">{a.reason}</p>
                {a.next_step && a.status !== "not_applicable" && <p className="text-muted">Investigator check: {humanize(a.next_step)}</p>}
                {a.evidence_ids.length > 0 && <EvidenceChips caseId={c.id} ids={a.evidence_ids} />}
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
