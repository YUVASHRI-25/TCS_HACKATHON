import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Play, Upload } from "lucide-react";
import { useDatasets, useRunDataset, useRuns, useUpload } from "@/hooks/useApi";
import { Badge, Button, Card, EmptyState, ErrorState, SkeletonRows } from "@/components/ui/primitives";
import { num, ts } from "@/lib/format";

const STATUS_TONE = { ready: "blue", active: "green", rejected: "red", running: "amber", succeeded: "green", failed: "red" } as const;

export function DatasetsPage() {
  const datasets = useDatasets();
  const runs = useRuns();
  const upload = useUpload();
  const runDs = useRunDataset();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const running = (runs.data ?? []).some((r) => r.status === "running");

  // When a run finishes, everything derived from the analysis is stale.
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && !running) {
      void qc.invalidateQueries();
    }
    wasRunning.current = running;
  }, [running, qc]);

  return (
    <div className="space-y-5 p-6">
      <h1 className="text-lg font-semibold">Datasets &amp; analysis runs</h1>
      <Card title="Upload transaction CSV files">
        <p className="mb-3 text-xs text-muted">
          Files must match the configured data format (see <code>config/mapping.yaml</code>): name each file after its table
          (e.g. <code>transactions.csv</code>) and include every mapped column. Tables you do not upload keep their configured
          source. Files in another format are rejected with the expected columns; nothing is guessed.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm"><span className="block text-xs text-muted">Dataset name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. October transactions"
              className="mt-1 w-64 rounded border border-line bg-canvas px-2 py-1.5" />
          </label>
          <label className="text-sm"><span className="block text-xs text-muted">CSV files</span>
            <input type="file" accept=".csv" multiple aria-label="CSV files"
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              className="mt-1 block text-xs file:mr-2 file:rounded file:border-0 file:bg-slate-700 file:px-2 file:py-1 file:text-slate-200" />
          </label>
          <Button variant="primary" disabled={!files.length || upload.isPending}
            onClick={() => upload.mutate({ name, files }, { onSuccess: () => { setFiles([]); setName(""); } })}>
            <Upload className="h-4 w-4" /> {upload.isPending ? "Uploading…" : "Upload & validate"}
          </Button>
        </div>
        {upload.isError && <div className="mt-3"><ErrorState error={upload.error} /></div>}
        {upload.data && (
          <p role="status" className={`mt-3 rounded border p-2 text-xs ${upload.data.status === "rejected" ? "border-red-500/30 bg-red-500/10 text-red-200" : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"}`}>
            {upload.data.status === "rejected" ? "Rejected: " : "Accepted: "}{upload.data.message}
          </p>
        )}
      </Card>

      <Card title="Datasets">
        {datasets.isLoading && <SkeletonRows rows={3} />}
        {datasets.isError && <ErrorState error={datasets.error} />}
        {datasets.data?.length === 0 && <EmptyState title="No datasets yet" />}
        <ul className="divide-y divide-line">
          {(datasets.data ?? []).map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
              <span className="font-mono text-xs text-muted">#{d.id}</span>
              <span className="font-medium">{d.name}</span>
              <Badge tone={STATUS_TONE[d.status]}>{d.status === "active" ? "analysed (current)" : d.status}</Badge>
              <span className="text-xs text-muted">by {d.created_by} · {ts(d.created_at)}</span>
              <span className="text-xs text-muted">{d.files.map((f) => `${f.table}${f.rows !== null ? ` (${num(f.rows)} rows)` : ""}`).join(", ")}</span>
              <Button className="ml-auto" disabled={d.status === "rejected" || running || runDs.isPending}
                onClick={() => runDs.mutate(d.id)}>
                <Play className="h-3.5 w-3.5" /> Run analysis
              </Button>
              {d.message && <p className="w-full text-xs text-muted">{d.message}</p>}
            </li>
          ))}
        </ul>
        {runDs.isError && <ErrorState error={runDs.error} />}
      </Card>

      <Card title="Processing history" actions={running ? <Badge tone="amber">analysis running…</Badge> : undefined}>
        {runs.data?.length === 0 && <EmptyState title="No analysis runs started from the console yet" />}
        <table className="w-full text-xs">
          <thead className="text-left text-muted"><tr><th className="py-1 font-medium">Run</th><th className="font-medium">Dataset</th><th className="font-medium">Started by</th><th className="font-medium">Started</th><th className="font-medium">Finished</th><th className="font-medium">Status</th><th className="font-medium">Result</th></tr></thead>
          <tbody>{(runs.data ?? []).map((r) => {
            const t = (r.summary?.tiers ?? null) as Record<string, number> | null;
            return (
              <tr key={r.id} className="border-t border-line align-top">
                <td className="py-1.5 font-mono">#{r.id}</td><td className="font-mono">#{r.dataset_id}</td><td>{r.triggered_by}</td>
                <td className="font-mono">{ts(r.started_at)}</td><td className="font-mono">{ts(r.finished_at)}</td>
                <td><Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge></td>
                <td>{r.error ? <span className="text-red-300">{r.error}</span> : t ? `HIGH ${t.HIGH} · MEDIUM ${t.MEDIUM} · LOW ${t.LOW} (${String(r.summary?.seconds)} s)` : "–"}</td>
              </tr>
            );
          })}</tbody>
        </table>
      </Card>
    </div>
  );
}
