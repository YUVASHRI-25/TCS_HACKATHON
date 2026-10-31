import { useEffect, useState } from "react";
import type { CaseOut, FactState } from "@/api/client";
import { useAdjudicate, useFacts, useNextBestActions, useWhatIf } from "@/hooks/useApi";
import { Badge, Button, Card, EmptyState, ErrorState, SkeletonRows, TierBadge } from "@/components/ui/primitives";

const STATES: FactState[] = ["unknown", "confirmed", "refuted"];

export function WhatIfPanel({ c }: { c: CaseOut }) {
  const facts = useFacts(c.id);
  const nba = useNextBestActions(c.id);
  const sim = useWhatIf(c.id);
  const record = useAdjudicate(c.id);
  const [state, setState] = useState<Record<string, FactState>>({});
  const [note, setNote] = useState("");

  useEffect(() => {
    if (facts.data) setState(Object.fromEntries(facts.data.map((f) => [f.id, f.state])));
  }, [facts.data]);
  useEffect(() => {
    if (Object.keys(state).length) sim.mutate(state);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  if (facts.isLoading) return <SkeletonRows />;
  if (facts.isError) return <ErrorState error={facts.error} />;
  const r = sim.data;
  const changed = (facts.data ?? []).filter((f) => state[f.id] && state[f.id] !== f.state);

  return (
    <div className="space-y-4">
      <Card title="What-if: facts an investigator can establish" actions={<Badge tone="amber">Simulation - not recorded</Badge>}>
        <div className="mb-4 flex items-center gap-6 rounded-md border border-line bg-panel2/50 p-3">
          <div><p className="text-[11px] uppercase text-muted">Current</p><p className="flex items-center gap-2 font-mono text-xl">{c.priority_score} <TierBadge tier={c.tier} /></p></div>
          <span className="text-muted" aria-hidden="true">→</span>
          <div aria-live="polite"><p className="text-[11px] uppercase text-muted">Simulated</p>
            {r ? <p className="flex items-center gap-2 font-mono text-xl transition-all">{r.score} <TierBadge tier={r.tier} /></p> : <p className="text-muted">…</p>}
          </div>
          {r && !r.still_opens_case && <p className="text-xs text-amber-300">Under these facts the network would no longer meet the two-signal case rule.</p>}
        </div>
        <ul className="divide-y divide-line">
          {(facts.data ?? []).map((f) => (
            <li key={f.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span>{f.label}{f.state !== "unknown" && <Badge tone="blue" className="ml-2">recorded: {f.state}</Badge>}</span>
              <div role="radiogroup" aria-label={f.label} className="flex overflow-hidden rounded-md border border-line text-xs">
                {STATES.map((s) => (
                  <button key={s} type="button" role="radio" aria-checked={state[f.id] === s}
                    onClick={() => setState((x) => ({ ...x, [f.id]: s }))}
                    className={`px-2.5 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 ${state[f.id] === s ? "bg-sky-600 text-white" : "hover:bg-slate-700/50"}`}>{s}</button>
                ))}
              </div>
            </li>
          ))}
        </ul>
        {r && r.changes.length > 0 && (
          <ul className="mt-3 space-y-0.5 text-xs text-muted">{r.changes.map((ch, i) => <li key={i}>{String(ch.fact)} → {String(ch.change).replace(/_/g, " ")} {String(ch.target)}{ch.to !== undefined ? ` = ${String(ch.to)}` : ""}</li>)}</ul>
        )}
        <div className="mt-4 space-y-2 border-t border-line pt-3">
          <label className="block text-xs text-muted" htmlFor="adj-note">Record a verified finding (requires a note; writes an audit entry)</label>
          <textarea id="adj-note" value={note} onChange={(e) => setNote(e.target.value)} rows={2} className="w-full rounded border border-line bg-canvas p-2 text-sm" placeholder="What was checked and how" />
          <div className="flex items-center gap-2">
            <Button variant="primary" disabled={!changed.length || !note.trim() || record.isPending}
              onClick={async () => { for (const f of changed) await record.mutateAsync({ fact: f.id, state: state[f.id]!, note }); setNote(""); }}>
              Record finding{changed.length > 1 ? `s (${changed.length})` : ""}
            </Button>
            {record.isError && <ErrorState error={record.error} />}
          </div>
        </div>
      </Card>
      <Card title="Next-best actions">
        {nba.isLoading && <SkeletonRows rows={3} />}
        {nba.data && nba.data.length === 0 && <EmptyState title="No unverified fact would change this score" />}
        <ol className="space-y-2">
          {(nba.data ?? []).map((a, i) => (
            <li key={a.fact} className="flex items-start gap-3 rounded-md border border-line p-2.5 text-sm">
              <span className="font-mono text-muted">{i + 1}</span>
              <div className="flex-1">
                <p>{a.label}</p>
                <p className="text-xs text-muted">{a.rationale} Expected shift {a.expected_shift} points
                  {a.effort_minutes ? ` · ~${a.effort_minutes} min (assumption)` : " · effort not configured (ranked by shift only)"}.</p>
              </div>
              <Button onClick={() => setState((x) => ({ ...x, [a.fact]: "confirmed" }))}>Do this check</Button>
            </li>
          ))}
        </ol>
        <p className="mt-2 text-xs text-muted">Expected shift weights both outcomes equally — an assumption, since outcome probabilities are not known.</p>
      </Card>
    </div>
  );
}
