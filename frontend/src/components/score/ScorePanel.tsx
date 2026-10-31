import type { CaseOut } from "@/api/client";
import { EvidenceChips } from "@/components/evidence/EvidenceChip";
import { Badge, Card, TierBadge } from "@/components/ui/primitives";
import { humanize } from "@/lib/format";
import { VIZ } from "@/lib/viz";

interface Step {
  label: string;
  points: number;
  kind: "signal" | "model" | "bonus" | "penalty" | "cap";
  note?: string;
  evidence?: string[];
}

/** Waterfall of the deterministic score: each signal's points, bonus, capped model points, penalties. */
export function ScorePanel({ c }: { c: CaseOut }) {
  const sb = c.score_breakdown;
  const steps: Step[] = [
    ...sb.signals.map((s) => ({ label: humanize(s.signal), points: s.points, kind: "signal" as const,
      note: `${s.weight} × strength ${s.strength.toFixed(2)}`, evidence: s.evidence_ids })),
    ...(sb.bonus ? [{ label: "Independent signal types bonus", points: sb.bonus, kind: "bonus" as const, note: "+5 per type beyond 2" }] : []),
    ...(sb.ml_signals.length ? [{ label: "Model signals (capped)", points: sb.ml_capped_total, kind: "model" as const,
      note: `raw ${sb.ml_raw_total} → capped at 20`, evidence: sb.ml_signals.flatMap((m) => m.evidence_ids) }] : []),
    ...sb.penalties.map((p) => ({ label: `Alternative: ${humanize(p.alternative)}`, points: p.points, kind: "penalty" as const,
      note: `fit ${p.fit.toFixed(2)} × ${p.weight}` })),
  ];
  const raw = steps.reduce((a, s) => a + s.points, 0);
  const scaleMax = Math.max(100, steps.reduce((a, s) => a + Math.max(0, s.points), 0));
  let run = 0;

  return (
    <div className="space-y-4">
      <Card title="Score waterfall" actions={<span className="flex items-center gap-2 text-xs"><TierBadge tier={sb.tier} /><span className="font-mono">{sb.total}</span></span>}>
        <p className="mb-3 text-xs text-muted">Priority score (0–100), not a probability. Every bar is a configured weight × a deterministic strength.</p>
        <div className="mb-2 flex gap-4 text-xs text-muted">
          <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: VIZ.primary }} /> adds points</span>
          <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: VIZ.contrast }} /> legitimate-explanation penalty</span>
        </div>
        <ol className="space-y-1.5">
          {steps.map((s) => {
            const start = run;
            run += s.points;
            const left = (Math.min(start, run) / scaleMax) * 100;
            const width = (Math.abs(s.points) / scaleMax) * 100;
            return (
              <li key={s.label} className="grid grid-cols-[13rem_1fr_4rem] items-center gap-3 text-xs">
                <div className="min-w-0">
                  <p className="truncate">{s.label} {s.kind === "model" && <Badge tone="violet">model</Badge>}</p>
                  <p className="text-[11px] text-muted">{s.note}</p>
                </div>
                <div className="relative h-4 rounded bg-slate-800/60" title={`${s.label}: ${s.points > 0 ? "+" : ""}${s.points}`}>
                  <div className="absolute top-0 h-4 rounded" style={{ left: `${left}%`, width: `${Math.max(width, 0.5)}%`, background: s.points < 0 ? VIZ.contrast : VIZ.primary }} />
                </div>
                <span className="tabular text-right font-mono">{s.points > 0 ? "+" : ""}{s.points.toFixed(1)}</span>
              </li>
            );
          })}
          <li className="grid grid-cols-[13rem_1fr_4rem] items-center gap-3 border-t border-line pt-2 text-xs font-semibold">
            <span>Total {raw > 100 || raw < 0 ? "(clipped to 0–100)" : ""}</span><span /><span className="text-right font-mono">{sb.total}</span>
          </li>
        </ol>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {steps.filter((s) => s.evidence?.length).map((s) => <span key={s.label} className="flex items-center gap-1 text-muted">{s.label}: <EvidenceChips caseId={c.id} ids={s.evidence!} /></span>)}
        </div>
      </Card>
      <Card title="Counterfactuals — what would change the tier">
        <table className="w-full text-xs">
          <thead className="text-left text-muted"><tr><th className="py-1 font-medium">If removed</th><th className="font-medium">Score</th><th className="font-medium">Tier</th><th className="font-medium">Still a case?</th></tr></thead>
          <tbody>{c.counterfactuals.map((cf) => (
            <tr key={cf.removed.join("+") + String(cf.minimal_tier_change)} className={`border-t border-line ${cf.minimal_tier_change ? "bg-sky-500/10" : ""}`}>
              <td className="py-1.5">{cf.removed.map(humanize).join(" + ")} {cf.minimal_tier_change && <Badge tone="blue">smallest set that lowers the tier</Badge>}</td>
              <td className="font-mono">{cf.score}</td>
              <td><TierBadge tier={cf.tier} /></td>
              <td>{cf.still_opens_case ? "yes" : "no — fewer than 2 deterministic signal types"}</td>
            </tr>
          ))}</tbody>
        </table>
      </Card>
    </div>
  );
}
