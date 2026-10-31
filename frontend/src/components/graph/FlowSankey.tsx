import { ResponsiveContainer, Sankey, Tooltip } from "recharts";
import type { CaseFlow } from "@/api/client";
import { EmptyState } from "@/components/ui/primitives";
import { short } from "@/lib/format";
import { VIZ } from "@/lib/viz";

interface LinkProps {
  sourceX: number; targetX: number; sourceY: number; targetY: number;
  sourceControlX: number; targetControlX: number; linkWidth: number;
  payload: { suspicious_amount: number; value: number };
}

function FlowLink(p: LinkProps) {
  const sus = p.payload.suspicious_amount > 0;
  return (
    <path
      d={`M${p.sourceX},${p.sourceY} C${p.sourceControlX},${p.sourceY} ${p.targetControlX},${p.targetY} ${p.targetX},${p.targetY}`}
      fill="none" stroke={sus ? VIZ.contrast : VIZ.neutral} strokeOpacity={sus ? 0.6 : 0.35} strokeWidth={Math.max(1, p.linkWidth)}
    />
  );
}

interface NodeProps { x: number; y: number; width: number; height: number; payload: { name: string } }

function FlowNode(p: NodeProps) {
  return (
    <g>
      <rect x={p.x} y={p.y} width={p.width} height={Math.max(2, p.height)} fill={VIZ.primary} rx={2} />
      <text x={p.x + p.width + 4} y={p.y + p.height / 2} fill={VIZ.text} fontSize={10} dominantBaseline="middle">{p.payload.name}</text>
    </g>
  );
}

/** Flow of funds among network members and their outside counterparties (Sankey).
 *  Sankey needs an acyclic layout, so reciprocal member-to-member flows keep only the larger direction. */
export function FlowSankey({ data }: { data: CaseFlow }) {
  if (!data.links.length) return <EmptyState title="No transactions involve these accounts" />;
  const top = [...data.links].sort((a, b) => b.amount - a.amount).slice(0, 40);
  const seen = new Set<string>();
  const acyclic = top.filter((l) => {
    const back = `${l.target}->${l.source}`;
    if (seen.has(back)) return false;
    seen.add(`${l.source}->${l.target}`);
    return true;
  });
  const ids = Array.from(new Set(acyclic.flatMap((l) => [l.source, l.target])));
  const label = new Map(data.nodes.map((n) => [n.id, n.label]));
  const sankey = {
    nodes: ids.map((id) => ({ name: label.get(id) ?? id })),
    links: acyclic.map((l) => ({ source: ids.indexOf(l.source), target: ids.indexOf(l.target), value: l.amount,
      suspicious_amount: l.suspicious_amount, n_txns: l.n_txns })),
  };
  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-4 text-xs text-muted">
        <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: VIZ.contrast }} /> includes evidence-cited transactions</span>
        <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: VIZ.neutral }} /> other flows</span>
        <span>Top {acyclic.length} flows by amount{data.currency_note ? ` · ${data.currency_note}` : ""}</span>
      </div>
      <div className="h-[28rem]" role="img" aria-label="Flow of funds Sankey diagram">
        <ResponsiveContainer>
          <Sankey data={sankey} nodePadding={12} nodeWidth={8} margin={{ top: 8, right: 140, bottom: 8, left: 8 }}
            link={(p: unknown) => <FlowLink {...(p as LinkProps)} />} node={(p: unknown) => <FlowNode {...(p as NodeProps)} />}>
            <Tooltip contentStyle={{ background: VIZ.surface, border: "1px solid #E2E8F0", fontSize: 12 }}
              formatter={(v: number) => short(v)} />
          </Sankey>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
