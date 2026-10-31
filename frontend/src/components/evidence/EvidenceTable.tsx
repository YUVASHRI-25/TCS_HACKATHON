import type { CaseOut } from "@/api/client";
import { Badge, Card } from "@/components/ui/primitives";
import { humanize, ts } from "@/lib/format";
import { EvidenceChip } from "./EvidenceChip";

export function EvidenceTable({ c }: { c: CaseOut }) {
  return (
    <Card title={`Evidence (${c.evidence.length}) — every item resolves to source rows`}>
      <div className="-m-4 overflow-auto">
        <table className="w-full text-xs">
          <thead className="bg-panel2 text-left text-muted">
            <tr><th className="px-3 py-2 font-medium">ID</th><th className="px-3 py-2 font-medium">Type</th><th className="px-3 py-2 font-medium">Description</th><th className="px-3 py-2 font-medium">Window</th><th className="px-3 py-2 text-right font-medium">Rows</th></tr>
          </thead>
          <tbody>{c.evidence.map((e) => (
            <tr key={e.id} className="border-t border-line align-top">
              <td className="px-3 py-2"><EvidenceChip caseId={c.id} eid={e.id} /></td>
              <td className="px-3 py-2"><div className="flex flex-col gap-1">{humanize(e.finding_type)}{e.source === "model" && <Badge tone="violet">model</Badge>}{e.finding_type === "regular_cadence" && <Badge tone="green">context</Badge>}</div></td>
              <td className="px-3 py-2 text-slate-300">{e.description}</td>
              <td className="whitespace-nowrap px-3 py-2 font-mono text-muted">{e.ts_min ? `${ts(e.ts_min).slice(0, 10)} → ${ts(e.ts_max).slice(0, 10)}` : "–"}</td>
              <td className="px-3 py-2 text-right font-mono">{e.n_source_rows}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </Card>
  );
}
