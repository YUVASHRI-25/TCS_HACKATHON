import { useUi } from "@/store/ui";

/** A citation chip: every claim in the UI links to an evidence item that resolves to source rows. */
export function EvidenceChip({ caseId, eid }: { caseId: string; eid: string }) {
  const open = useUi((s) => s.openEvidence);
  return (
    <button
      type="button"
      onClick={() => open(caseId, eid)}
      className="rounded bg-sky-500/15 px-1.5 py-0.5 font-mono text-[11px] text-sky-300 hover:bg-sky-500/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
      aria-label={`Open evidence ${eid}`}
    >
      {eid}
    </button>
  );
}

export function EvidenceChips({ caseId, ids }: { caseId: string; ids: string[] }) {
  if (!ids.length) return <span className="text-xs text-muted">–</span>;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {ids.map((e) => <EvidenceChip key={e} caseId={caseId} eid={e} />)}
    </span>
  );
}
