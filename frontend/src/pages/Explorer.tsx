import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { FolderPlus } from "lucide-react";
import { useCases, useCreateCase, useEntitySearch, useNeighbors } from "@/hooks/useApi";
import { CaseGraph } from "@/components/graph/CaseGraph";
import { Button, Card, EmptyState, ErrorState, SkeletonRows } from "@/components/ui/primitives";
import type { CaseGraph as CaseGraphData } from "@/api/client";

interface RawGraph { nodes: { id: string; type?: string; derived?: boolean }[]; edges: { source: string; target: string; type: string; confidence?: number; amount?: number; n_txns?: number; first_ts?: string; provenance?: { table: string; row: number } | null }[] }

function CreateCasePanel({ accounts, centre }: { accounts: string[]; centre: string }) {
  const navigate = useNavigate();
  const create = useCreateCase();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  useEffect(() => { setPicked(new Set(accounts.includes(centre) ? [centre] : [])); }, [accounts, centre]);
  return (
    <Card title="Create an investigation case from these accounts">
      <p className="mb-2 text-xs text-muted">TRACE assembles the case from the latest analysis findings for the accounts you choose, using the same evidence and scoring rules.</p>
      <div className="mb-3 flex max-h-32 flex-wrap gap-1.5 overflow-auto">
        {accounts.map((a) => (
          <label key={a} className={`flex cursor-pointer items-center gap-1 rounded border px-2 py-0.5 font-mono text-xs ${picked.has(a) ? "border-sky-500 bg-sky-500/15" : "border-line"}`}>
            <input type="checkbox" className="accent-sky-500" checked={picked.has(a)}
              onChange={() => setPicked((p) => { const n = new Set(p); if (n.has(a)) n.delete(a); else n.add(a); return n; })} />
            {a.replace("account:", "")}
          </label>
        ))}
        {accounts.length === 0 && <p className="text-xs text-muted">No accounts in this neighbourhood.</p>}
      </div>
      <div className="grid gap-2 md:grid-cols-[16rem_1fr_auto]">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Case title (optional)" aria-label="Case title"
          className="rounded border border-line bg-canvas px-2 py-1.5 text-sm" />
        <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Why are you opening this case? (required)" aria-label="Reason for opening the case"
          className="rounded border border-line bg-canvas px-2 py-1.5 text-sm" />
        <Button variant="primary" disabled={!picked.size || !notes.trim() || create.isPending}
          onClick={() => create.mutate({ accounts: [...picked], title, notes }, { onSuccess: (c) => navigate(`/cases/${c.id}`) })}>
          <FolderPlus className="h-4 w-4" /> Create case ({picked.size})
        </Button>
      </div>
      {create.isError && <div className="mt-2"><ErrorState error={create.error} /></div>}
    </Card>
  );
}

export function ExplorerPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const node = params.get("node");
  const [hops, setHops] = useState(1);
  const [q, setQ] = useState("");
  const search = useEntitySearch(q);
  const nb = useNeighbors(node, hops);
  const flagged = useCases({});

  const graph = useMemo<CaseGraphData | null>(() => {
    const raw = nb.data as RawGraph | undefined;
    if (!raw) return null;
    return {
      truncated: false,
      nodes: raw.nodes.map((n) => ({ id: n.id, type: n.type ?? "entity", label: n.id.split(":").slice(1).join(":"),
        role: n.id === node ? "member" : "related", derived: !!n.derived, risk: 0, suspicious: false, evidence_ids: [] })),
      edges: raw.edges.map((e, i) => ({ id: `e${i}`, source: e.source, target: e.target, type: e.type, suspicious: false,
        evidence_ids: [], confidence: e.confidence ?? null, amount: e.amount ?? null, ts: e.first_ts ?? null,
        n_txns: e.n_txns ?? null, provenance: e.provenance ? `${e.provenance.table} row ${e.provenance.row}` : null } as CaseGraphData["edges"][number])),
    };
  }, [nb.data, node]);
  const accounts = useMemo(() => (graph?.nodes ?? []).filter((n) => n.type === "account").map((n) => n.id).sort(), [graph]);

  return (
    <div className="flex flex-col gap-4 p-6">
      <h1 className="text-lg font-semibold">Network explorer</h1>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find an entity (account, customer, device, IPâ€¦)" aria-label="Find entity"
          className="w-80 rounded border border-line bg-panel px-2 py-1" />
        <label className="flex items-center gap-2"><span className="text-muted">Hops</span>
          <select value={hops} onChange={(e) => setHops(Number(e.target.value))} className="rounded border border-line bg-panel px-2 py-1">
            <option value={1}>1</option><option value={2}>2</option>
          </select>
        </label>
        {node && <span className="font-mono text-xs text-muted">centre: {node}{graph ? ` · ${graph.nodes.length} entities · ${graph.edges.length} links` : ""}</span>}
      </div>
      {q && (
        <ul className="flex flex-wrap gap-1.5">
          {(search.data ?? []).map((e) => (
            <li key={e.id}><button type="button" onClick={() => { setParams({ node: e.id }); setQ(""); }}
              className="rounded border border-line px-2 py-0.5 font-mono text-xs hover:bg-slate-700/50">{e.id}{e.type ? <span className="ml-1 text-muted">· {e.type}</span> : null}</button></li>
          ))}
          {search.data?.length === 0 && <li className="text-xs text-muted">No entity matches</li>}
        </ul>
      )}
      <Card className="[&>div]:p-0">
        {!node && (
          <div className="p-6">
            <EmptyState title="Search for an entity to explore its neighbourhood" />
            <p className="mt-2 text-center text-xs text-muted">Search by account, customer, device, IP, merchant or beneficiary id (e.g. a few digits of an id), or start from a flagged network:</p>
            <div className="mt-3 flex flex-wrap justify-center gap-1.5">
              {(flagged.data ?? []).slice(0, 8).map((c) => (
                <button key={c.id} type="button" onClick={() => navigate(`/cases/${c.id}`)}
                  className="rounded border border-line px-2 py-1 text-xs hover:bg-sky-500/10">
                  <span className="font-mono">{c.id}</span> · {c.tier} · {c.priority_score}
                </button>
              ))}
              {flagged.isError && <ErrorState error={flagged.error} />}
            </div>
          </div>
        )}
        {node && nb.isLoading && <div className="p-4"><SkeletonRows /></div>}
        {node && nb.isError && <div className="p-4"><ErrorState error={nb.error} /></div>}
        {graph && <div className="h-[32rem]"><CaseGraph caseId="" data={graph} /></div>}
      </Card>
      {graph && node && <CreateCasePanel accounts={accounts} centre={node} />}
    </div>
  );
}
