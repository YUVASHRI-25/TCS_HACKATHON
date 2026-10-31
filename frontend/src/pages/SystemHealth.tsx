import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { jsonCall } from "@/api/client";
import { Badge, Button, Card, ErrorState, SkeletonRows } from "@/components/ui/primitives";

type Obj = Record<string, unknown>;
interface Health { backend: Obj; database: Obj; graph: Obj; llm: Obj }
interface CaseRow { id: string; tier: string; priority_score: number; status: string; origin?: string; created_by?: string | null; summary: string }

function Row({ k, v }: { k: string; v: unknown }) {
  return <div className="flex justify-between gap-4 py-0.5 text-sm"><span className="text-muted">{k}</span><span className="break-all text-right font-mono text-xs">{v === null || v === undefined ? "–" : String(v)}</span></div>;
}

export function SystemPage() {
  const h = useQuery({ queryKey: ["sys-health"], queryFn: () => jsonCall<Health>("GET", "/api/admin/system-health"), refetchInterval: 30000 });
  const cases = useQuery({ queryKey: ["admin-cases"], queryFn: () => jsonCall<CaseRow[]>("GET", "/api/admin/cases") });
  const d = h.data;
  return (
    <div className="space-y-5 p-6">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold">System health &amp; investigations</h1>
        <Button onClick={() => void h.refetch()} disabled={h.isFetching}><RefreshCw className={`mr-1 inline h-3.5 w-3.5 ${h.isFetching ? "animate-spin" : ""}`} />Re-check</Button>
      </div>
      {h.isLoading && <SkeletonRows rows={4} />}
      {h.isError && <ErrorState error={h.error} />}
      {d && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Card title="Backend" actions={<Badge tone="green">{String(d.backend.status)}</Badge>}><Row k="API" v="responding" /></Card>
          <Card title="Database" actions={<Badge tone={d.database.connected ? "green" : "red"}>{d.database.connected ? "connected" : "disconnected"}</Badge>}>
            {Object.entries(d.database).filter(([k]) => k !== "connected").map(([k, v]) => <Row key={k} k={k} v={v} />)}</Card>
          <Card title="Graph AI" actions={<Badge tone={d.graph.status === "ready" ? "green" : "amber"}>{String(d.graph.status)}</Badge>}>
            {Object.entries(d.graph).filter(([k]) => k !== "status").map(([k, v]) => <Row key={k} k={k} v={v} />)}</Card>
          <Card title="LLM provider" actions={<Badge tone={d.llm.connected ? "green" : "red"}>{d.llm.connected ? "connected" : "not connected"}</Badge>}>
            {(["model", "base_url", "api_key_set", "latency_ms", "requests_since_start", "failures_since_start", "persisted_calls", "persisted_failures"] as const).map((k) => <Row key={k} k={k} v={d.llm[k]} />)}
            {d.llm.error ? <p className="mt-2 text-xs text-red-300">Connection error: {String(d.llm.error)}</p> : null}
            {d.llm.last_error ? <p className="mt-1 text-xs text-amber-300">Last request failure: {String(d.llm.last_error)}</p> : null}
          </Card>
        </div>
      )}
      <Card title="All investigation cases (system-wide)">
        {cases.isLoading && <SkeletonRows rows={4} />}
        {cases.isError && <ErrorState error={cases.error} />}
        {cases.data && (cases.data.length === 0 ? <p className="text-sm text-muted">No cases exist. Run the analysis on a dataset first.</p> : (
          <div className="max-h-96 overflow-auto"><table className="w-full text-sm">
            <thead className="text-left text-xs text-muted"><tr><th className="py-1">Case</th><th>Tier</th><th>Score</th><th>Status</th><th>Origin</th></tr></thead>
            <tbody>{cases.data.map((r) => <tr key={r.id} className="border-t border-line">
              <td className="py-1"><Link className="font-mono text-sky-300 hover:underline" to={`/cases/${r.id}`}>{r.id}</Link></td>
              <td>{r.tier}</td><td className="font-mono">{r.priority_score}</td><td>{r.status}</td><td>{r.origin ?? "pipeline"}{r.created_by ? ` · ${r.created_by}` : ""}</td></tr>)}</tbody>
          </table></div>))}
      </Card>
    </div>
  );
}
