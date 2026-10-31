import { useState } from "react";
import { BadgeCheck, ShieldX } from "lucide-react";
import type { CaseOut } from "@/api/client";
import { useAudit, useReview } from "@/hooks/useApi";
import { useAuth } from "@/store/auth";
import { Badge, Button, Card, EmptyState, ErrorState, SkeletonRows } from "@/components/ui/primitives";
import { humanize, ts } from "@/lib/format";

type Action = "start_review" | "escalate" | "resolve" | "reopen";
type Resolution = "no_further_action" | "false_positive" | "referred_for_further_investigation";

const ACTIONS: { id: Action; label: string; from: string[] }[] = [
  { id: "start_review", label: "Mark under review", from: ["open"] },
  { id: "escalate", label: "Escalate to senior investigator", from: ["open", "under_review"] },
  { id: "resolve", label: "Resolve", from: ["open", "under_review", "escalated"] },
  { id: "reopen", label: "Reopen", from: ["under_review", "escalated", "resolved"] },
];
const RESOLUTIONS: { id: Resolution; label: string }[] = [
  { id: "no_further_action", label: "No further action" },
  { id: "false_positive", label: "False positive" },
  { id: "referred_for_further_investigation", label: "Referred for further investigation" },
];
const FLOW = ["open", "under_review", "escalated", "resolved"];

export function ReviewPanel({ c }: { c: CaseOut }) {
  const user = useAuth((s) => s.user);
  const [notes, setNotes] = useState("");
  const [resolution, setResolution] = useState<Resolution>("no_further_action");
  const review = useReview(c.id);
  const status = FLOW.includes(c.status) ? c.status : "open"; // statuses from an earlier workflow version
  const available = ACTIONS.filter((a) => a.from.includes(status));
  return (
    <Card title="Case status — human decision">
      <ol className="mb-3 flex items-center gap-1 text-xs" aria-label="Case status">
        {FLOW.map((s, i) => (
          <li key={s} className="flex items-center gap-1">
            <span className={`rounded px-2 py-0.5 ${status === s ? "bg-sky-600 text-white" : "bg-slate-700/40 text-muted"}`} aria-current={status === s ? "step" : undefined}>{humanize(s)}</span>
            {i < FLOW.length - 1 && <span className="text-muted" aria-hidden="true">→</span>}
          </li>
        ))}
      </ol>
      <p className="mb-3 text-xs text-muted">TRACE makes no determination. Escalation goes to a senior investigator inside the institution; nothing is filed, frozen or submitted. Recorded as <span className="text-slate-300">{user?.display_name}</span>.</p>
      <label className="block text-xs text-muted" htmlFor="notes">Notes (required)</label>
      <textarea id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className="mt-1 w-full rounded border border-line bg-canvas p-2 text-sm" placeholder="Rationale for this status change" />
      {available.some((a) => a.id === "resolve") && (
        <label className="mt-2 flex items-center gap-2 text-xs"><span className="text-muted">Outcome if resolving</span>
          <select value={resolution} onChange={(e) => setResolution(e.target.value as Resolution)} className="rounded border border-line bg-canvas px-2 py-1">
            {RESOLUTIONS.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
          </select>
        </label>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {available.map((a) => (
          <Button key={a.id} variant={a.id === "start_review" ? "primary" : "default"} disabled={!notes.trim() || review.isPending}
            onClick={() => review.mutate({ action: a.id, notes, resolution: a.id === "resolve" ? resolution : undefined }, { onSuccess: () => setNotes("") })}>{a.label}</Button>
        ))}
      </div>
      {review.isError && <div className="mt-2"><ErrorState error={review.error} /></div>}
      {review.isSuccess && <p className="mt-2 text-xs text-emerald-300" role="status">Recorded. Status is now {humanize(review.data.case.status)}; audit entry #{review.data.audit_entry.seq} appended.</p>}
    </Card>
  );
}

export function AuditPanel({ caseId }: { caseId: string }) {
  const q = useAudit(caseId);
  if (q.isLoading) return <SkeletonRows />;
  if (q.isError) return <ErrorState error={q.error} />;
  const a = q.data!;
  return (
    <Card title="Audit trail (append-only, hash-chained)" actions={a.chain_valid
      ? <Badge tone="green"><BadgeCheck className="h-3 w-3" /> chain verified ({a.chain_entries} entries)</Badge>
      : <Badge tone="red"><ShieldX className="h-3 w-3" /> chain broken at #{a.broken_at_seq}</Badge>}>
      {a.entries.length === 0 ? <EmptyState title="No human action recorded for this case yet" /> : (
        <ol className="space-y-2">
          {a.entries.map((e) => (
            <li key={e.seq} className="rounded-md border border-line p-2.5 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-muted">#{e.seq}</span>
                <span className="font-medium">{humanize(e.action)}</span>
                {typeof e.payload.resolution === "string" && <Badge tone="green">{humanize(e.payload.resolution)}</Badge>}
                <span>by {e.actor}</span>
                <span className="ml-auto font-mono text-muted">{ts(e.ts)}</span>
              </div>
              <p className="mt-1 text-slate-300">{String(e.payload.notes ?? e.payload.note ?? "")}</p>
              <p className="mt-1 break-all font-mono text-[10px] text-muted">hash {e.hash} ← prev {e.prev_hash.slice(0, 16)}…</p>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
