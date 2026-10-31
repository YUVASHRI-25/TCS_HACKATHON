import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { ArrowLeft, FileDown } from "lucide-react";
import { useCase, useCaseFlow, useCaseGraph } from "@/hooks/useApi";
import { Badge, Card, EmptyState, ErrorState, Skeleton, SkeletonRows, TierBadge } from "@/components/ui/primitives";
import { CaseGraph } from "@/components/graph/CaseGraph";
import { FlowSankey } from "@/components/graph/FlowSankey";
import { EvidenceChips } from "@/components/evidence/EvidenceChip";
import { EvidenceTable } from "@/components/evidence/EvidenceTable";
import { HypothesesPanel } from "@/components/hypotheses/HypothesesPanel";
import { ScorePanel } from "@/components/score/ScorePanel";
import { NarrativePanel } from "@/components/narrative/NarrativePanel";
import { ChatDrawer } from "@/components/chat/ChatDrawer";
import { ExplainButton } from "@/components/chat/ExplainButton";
import { useMediaQuery } from "@/lib/useMediaQuery";
import { useUi } from "@/store/ui";
import { WhatIfPanel } from "@/components/whatif/WhatIfPanel";
import { AuditPanel, ReviewPanel } from "@/components/review/ReviewPanel";
import { byCurrency, humanize, num } from "@/lib/format";
import { download, type CaseOut } from "@/api/client";

const TABS = ["Overview", "Hypotheses", "Evidence", "Score", "Flow", "Narrative", "Next steps", "What-if", "Audit"] as const;
type TabId = (typeof TABS)[number];

function Overview({ c }: { c: CaseOut }) {
  const kq = c.key_questions;
  const ex = c.exposure;
  return (
    <div className="space-y-4">
      <Card title="Summary"><p className="text-sm leading-relaxed">{c.summary}</p>
        <div className="mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-violet-500/20 bg-gradient-to-r from-violet-500/5 to-sky-500/5 p-3">
          <ExplainButton caseId={c.id} prominent />
          <p className="min-w-0 flex-1 text-xs text-muted">Not sure why this network was flagged? Get a plain-language explanation based only on this case's evidence, then ask follow-up questions.</p>
        </div>
        {!c.meets_case_rule && <p className="mt-2 text-xs text-amber-300">Opened by an investigator; it does not meet the automatic two-signal case rule.</p>}
      </Card>
      {c.tier === "LOW" && (
        <Card title="Why was this downgraded?">
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {c.score_breakdown.penalties.map((p) => <li key={p.alternative}>{humanize(p.alternative)} explanation fits ({p.fit.toFixed(2)}), removing {Math.abs(p.points)} points.</li>)}
            {c.score_breakdown.signals.length <= 2 && <li>Only {c.score_breakdown.signals.length} independent deterministic signal types, so no multi-signal bonus applies.</li>}
            <li>Total {c.priority_score} is below the MEDIUM cut-off.</li>
          </ul>
        </Card>
      )}
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="1 · Why is it suspicious?">
          <ul className="space-y-2 text-sm">{kq.why_suspicious.map((w) => <li key={w.signal} className="flex flex-wrap items-center gap-2">{w.label} <EvidenceChips caseId={c.id} ids={w.evidence_ids} /></li>)}</ul>
        </Card>
        <Card title="2 · What evidence supports it?">
          <p className="text-sm">{c.evidence.length} evidence items, {c.evidence.filter((e) => e.source === "model").length} of them model signals.</p>
          <p className="mt-1 text-xs text-muted">Flagged transactions: {num(ex.suspicious_txns)} · {byCurrency(ex.by_currency)}</p>
          {ex.note && <p className="text-xs text-amber-300/80">{ex.note}</p>}
          <div className="mt-2"><EvidenceChips caseId={c.id} ids={c.evidence.map((e) => e.id)} /></div>
        </Card>
        <Card title="3 · What legitimate explanation might exist?">
          <ul className="space-y-1.5 text-sm">{kq.legitimate_explanations.map((a) => (
            <li key={a.id}><span className="font-medium">{a.label}</span>{" "}
              {a.status === "cannot_evaluate" ? <Badge tone="amber">cannot evaluate</Badge> : <span className="font-mono text-xs">fit {a.fit?.toFixed(2)}</span>}
              <p className="text-xs text-muted">{a.reason}</p></li>
          ))}</ul>
        </Card>
        <Card title="4 · What should an investigator examine next?">
          <ol className="list-decimal space-y-1 pl-5 text-sm">{kq.next_steps.map((s) => <li key={s}>{s}</li>)}</ol>
        </Card>
      </div>
      <ReviewPanel c={c} />
    </div>
  );
}

function NextSteps({ c }: { c: CaseOut }) {
  const [done, setDone] = useState<Set<string>>(new Set());
  return (
    <Card title="Investigator checklist (never punitive)">
      <ul className="space-y-2">{c.next_steps.map((s) => (
        <li key={s.id} className="flex items-start gap-2 text-sm">
          <input id={`ns-${s.id}`} type="checkbox" className="mt-1 accent-sky-500" checked={done.has(s.id)}
            onChange={() => setDone((d) => { const n = new Set(d); if (n.has(s.id)) n.delete(s.id); else n.add(s.id); return n; })} />
          <label htmlFor={`ns-${s.id}`}><span className="font-medium">{s.label}</span><span className="block text-xs text-muted">{s.description} — {s.reason}</span></label>
        </li>
      ))}</ul>
      <p className="mt-3 text-xs text-muted">Checklist ticks are local to this browser. Record verified facts in the What-if tab to write them to the audit trail.</p>
    </Card>
  );
}

export function CaseWorkspacePage() {
  const { caseId = "" } = useParams();
  const q = useCase(caseId);
  const graph = useCaseGraph(caseId);
  const flow = useCaseFlow(caseId);
  const [tab, setTab] = useState<TabId>("Overview");
  const wide = useMediaQuery("(min-width: 1024px)");
  const closeChat = useUi((s) => s.closeChat);
  useEffect(() => () => closeChat(), [closeChat, caseId]);   // never leave a chat open on another case

  if (q.isLoading) return <div className="p-6"><SkeletonRows rows={12} /></div>;
  if (q.isError) return <div className="p-6"><ErrorState error={q.error} /></div>;
  const c = q.data!;
  const members = c.entities.filter((e) => e.role === "member").length;

  return (
    <div className="flex h-full min-h-0">
    <div className="flex h-full min-w-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line bg-panel px-4 py-2.5">
        <Link to="/cases" className="rounded p-1 text-muted hover:text-slate-200" aria-label="Back to case queue"><ArrowLeft className="h-4 w-4" /></Link>
        <h1 className="font-mono text-sm">{c.id}</h1>
        <TierBadge tier={c.tier} />
        <span className="font-mono text-sm">{c.priority_score}</span>
        <span className="text-xs text-muted">priority score</span>
        <Badge>{humanize(c.status)}</Badge>
        <span className="text-xs text-muted">{members} accounts · {c.evidence.length} evidence</span>
        {c.adjudicated && <Badge tone="blue">after recorded facts: {c.adjudicated.score} ({c.adjudicated.tier})</Badge>}
        {c.origin === "investigator" && <Badge tone="violet">investigator-created by {c.created_by}</Badge>}
        {c.resolution && <Badge tone="green">outcome: {humanize(c.resolution)}</Badge>}
        <span className="ml-auto" />
        <ExplainButton caseId={c.id} />
        <button type="button" onClick={() => void download(`/api/cases/${c.id}/dossier.pdf`, `TRACE-${c.id}-dossier.pdf`)}
          className="inline-flex items-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-sm hover:bg-slate-700/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400">
          <FileDown className="h-4 w-4" aria-hidden="true" /> Dossier PDF
        </button>
      </div>
      <PanelGroup direction={wide ? "horizontal" : "vertical"} className="min-h-0 flex-1">
        <Panel defaultSize={45} minSize={25}>
          {graph.isLoading && <Skeleton className="m-4 h-[calc(100%-2rem)]" />}
          {graph.isError && <div className="p-4"><ErrorState error={graph.error} /></div>}
          {graph.data && (graph.data.nodes.length ? <CaseGraph caseId={c.id} data={graph.data} /> : <EmptyState title="No graph data for this case" />)}
        </Panel>
        <PanelResizeHandle className={`${wide ? "w-1" : "h-1"} bg-line transition-colors hover:bg-sky-500`} aria-label="Resize panels" />
        <Panel defaultSize={55} minSize={30}>
          <div className="flex h-full flex-col">
            <div role="tablist" aria-label="Case sections" className="flex gap-0.5 overflow-x-auto border-b border-line px-2">
              {TABS.map((t) => (
                <button key={t} role="tab" aria-selected={tab === t} type="button" onClick={() => setTab(t)}
                  className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 ${tab === t ? "border-sky-400 text-slate-100" : "border-transparent text-muted hover:text-slate-200"}`}>{t}</button>
              ))}
            </div>
            <div role="tabpanel" className="min-h-0 flex-1 overflow-auto p-4">
              {tab === "Overview" && <Overview c={c} />}
              {tab === "Hypotheses" && <HypothesesPanel c={c} />}
              {tab === "Evidence" && <EvidenceTable c={c} />}
              {tab === "Score" && <ScorePanel c={c} />}
              {tab === "Flow" && <Card title="Flow of funds">{flow.isLoading ? <SkeletonRows /> : flow.isError ? <ErrorState error={flow.error} /> : <FlowSankey data={flow.data!} />}</Card>}
              {tab === "Narrative" && <NarrativePanel c={c} />}
              {tab === "Next steps" && <NextSteps c={c} />}
              {tab === "What-if" && <WhatIfPanel c={c} />}
              {tab === "Audit" && <AuditPanel caseId={c.id} />}
            </div>
          </div>
        </Panel>
      </PanelGroup>
    </div>
    <ChatDrawer c={c} docked={wide} />
    </div>
  );
}
