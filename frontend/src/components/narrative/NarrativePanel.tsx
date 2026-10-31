import type { CaseOut } from "@/api/client";
import { EvidenceChips } from "@/components/evidence/EvidenceChip";
import { Badge, Card } from "@/components/ui/primitives";
import { humanize } from "@/lib/format";

/** Investigation narrative assembled from the case's structured fields (template mode, LLM_PROVIDER=none).
 *  Every factual sentence is an evidence description and carries its citation. */
export function NarrativePanel({ c }: { c: CaseOut }) {
  const byId = new Map(c.evidence.map((e) => [e.id, e]));
  const kq = c.key_questions;
  return (
    <Card title="Investigation narrative" actions={<Badge tone="slate">template · no LLM</Badge>}>
      <div className="space-y-5 text-sm leading-relaxed">
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">Why this network requires human investigation</h3>
          <p>{c.summary}</p>
        </section>
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">Evidence</h3>
          <ul className="space-y-2">
            {kq.why_suspicious.flatMap((w) => w.evidence_ids.slice(0, 3).map((eid) => (
              <li key={eid} className="flex gap-2"><span>{byId.get(eid)?.description}</span><EvidenceChips caseId={c.id} ids={[eid]} /></li>
            )))}
          </ul>
        </section>
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">Legitimate explanations considered</h3>
          <ul className="list-disc space-y-1 pl-5">
            {kq.legitimate_explanations.map((a) => (
              <li key={a.id}><span className="font-medium">{a.label}</span> — {a.status === "cannot_evaluate" ? "cannot be evaluated from the data: " : a.fit !== null ? `fit ${a.fit.toFixed(2)}: ` : ""}{a.reason}</li>
            ))}
          </ul>
        </section>
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">Recommended next steps</h3>
          <ul className="list-disc space-y-1 pl-5">{c.next_steps.map((s) => <li key={s.id}>{s.label} — <span className="text-muted">{s.reason}</span></li>)}</ul>
        </section>
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">Confidence and limits</h3>
          <p className="text-slate-300">The priority score is {c.priority_score} ({c.tier}); it ranks where to look first and is not a probability. Capabilities not evaluated on this data: {c.capabilities_disabled.map((d) => humanize(d.id)).join(", ") || "none"}.</p>
          <p className="mt-1 text-xs text-muted">{c.guardrail_notice}</p>
        </section>
      </div>
    </Card>
  );
}
