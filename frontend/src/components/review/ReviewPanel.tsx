import { useState } from "react";
import { BadgeCheck, ShieldX } from "lucide-react";
import type { CaseOut } from "@/api/client";
import { useAudit, useReview } from "@/hooks/useApi";
import { useUi } from "@/store/ui";
import { Badge, Button, Card, EmptyState, ErrorState, SkeletonRows } from "@/components/ui/primitives";
import { humanize, ts } from "@/lib/format";

const ACTIONS = [
  { id: "confirm_for_investigation", label: "Confirm for investigation" },
  { id: "request_more_info", label: "Request more information" },
  { id: "reject_false_positive", label: "Reject as false positive" },
] as const;

export function ReviewPanel({ c }: { c: CaseOut }) {
  const reviewer = useUi((s) => s.reviewer);
  const setReviewer = useUi((s) => s.setReviewer);
  const [notes, setNotes] = useState("");
  const review = useReview(c.id);
  return (
    <Card title="Human review">
      <p className="mb-3 text-xs text-muted">TRACE makes no determination. These actions record a human decision about whether to investigate; nothing is filed, frozen or submitted.</p>
      <div className="grid gap-2 md:grid-cols-[12rem_1fr]">
        <label className="text-xs text-muted" htmlFor="reviewer">Reviewer</label>
        <input id="reviewer" value={reviewer} onChange={(e) => setReviewer(e.target.value)} className="rounded border border-line bg-canvas px-2 py-1 text-sm" placeholder="Your name or ID" />
        <label className="text-xs text-muted" htmlFor="notes">Notes (required)</label>
        <textarea id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className="rounded border border-line bg-canvas p-2 text-sm" placeholder="Rationale for this decision" />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {ACTIONS.map((a) => (
          <Button key={a.id} variant={a.id === "confirm_for_investigation" ? "primary" : "default"} disabled={!notes.trim() || !reviewer.trim() || review.isPending}
            onClick={() => review.mutate({ action: a.id, reviewer, notes }, { onSuccess: () => setNotes("") })}>{a.label}</Button>
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
