import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useEntitySearch, useNeighbors } from "@/hooks/useApi";
import { CaseGraph } from "@/components/graph/CaseGraph";
import { Card, EmptyState, ErrorState, SkeletonRows } from "@/components/ui/primitives";
import type { CaseGraph as CaseGraphData } from "@/api/client";

interface RawGraph { nodes: { id: string; type?: string; derived?: boolean }[]; edges: { source: string; target: string; type: string; confidence?: number }[] }

export function ExplorerPage() {
  const [params, setParams] = useSearchParams();
  const node = params.get("node");
  const [hops, setHops] = useState(1);
  const [q, setQ] = useState("");
  const search = useEntitySearch(q);
  const nb = useNeighbors(node, hops);

  const graph = useMemo<CaseGraphData | null>(() => {
    const raw = nb.data as RawGraph | undefined;
    if (!raw) return null;
    return {
      truncated: false,
      nodes: raw.nodes.map((n) => ({ id: n.id, type: n.type ?? "entity", label: n.id.split(":").slice(1).join(":"),
        role: n.id === node ? "member" : "related", derived: !!n.derived, risk: 0, suspicious: false, evidence_ids: [] })),
      edges: raw.edges.map((e, i) => ({ id: `e${i}`, source: e.source, target: e.target, type: e.type, suspicious: false,
        evidence_ids: [], confidence: e.confidence ?? null })),
    };
  }, [nb.data, node]);

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <h1 className="text-lg font-semibold">Network explorer</h1>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find an entity (account, customer, device, IP…)" aria-label="Find entity"
          className="w-80 rounded border border-line bg-panel px-2 py-1" />
        <label className="flex items-center gap-2"><span className="text-muted">Hops</span>
          <select value={hops} onChange={(e) => setHops(Number(e.target.value))} className="rounded border border-line bg-panel px-2 py-1">
            <option value={1}>1</option><option value={2}>2</option>
          </select>
        </label>
        {node && <span className="font-mono text-xs text-muted">centre: {node}</span>}
      </div>
      {q && (
        <ul className="flex flex-wrap gap-1.5">
          {(search.data ?? []).map((e) => (
            <li key={e.id}><button type="button" onClick={() => { setParams({ node: e.id }); setQ(""); }}
              className="rounded border border-line px-2 py-0.5 font-mono text-xs hover:bg-slate-700/50">{e.id}</button></li>
          ))}
          {search.data?.length === 0 && <li className="text-xs text-muted">No entity matches</li>}
        </ul>
      )}
      <Card className="min-h-0 flex-1 [&>div]:h-full [&>div]:p-0">
        {!node && <EmptyState title="Search for an entity to explore its neighbourhood" />}
        {node && nb.isLoading && <div className="p-4"><SkeletonRows /></div>}
        {node && nb.isError && <div className="p-4"><ErrorState error={nb.error} /></div>}
        {graph && <div className="h-[36rem]"><CaseGraph caseId="" data={graph} /></div>}
      </Card>
    </div>
  );
}
