import { useEffect, useMemo, useRef, useState } from "react";
import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import fcose from "cytoscape-fcose";
import { Maximize2, Pause, Play } from "lucide-react";
import type { CaseGraph as CaseGraphData, GraphNode } from "@/api/client";
import { useNeighbors } from "@/hooks/useApi";
import { NODE_STYLE, VIZ } from "@/lib/viz";
import { humanize, num, ts } from "@/lib/format";
import { Badge, Button } from "@/components/ui/primitives";
import { EvidenceChips } from "@/components/evidence/EvidenceChip";

cytoscape.use(fcose);

interface Props {
  caseId: string;
  data: CaseGraphData;
}

export function CaseGraph({ caseId, data }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [expand, setExpand] = useState<string | null>(null);
  const neighbors = useNeighbors(expand, 1);

  const types = useMemo(() => Array.from(new Set(data.nodes.map((n) => n.type))).sort(), [data.nodes]);
  const times = useMemo(
    () => data.edges.filter((e) => e.ts).map((e) => new Date(e.ts!).getTime()).sort((a, b) => a - b),
    [data.edges],
  );
  const [cutoff, setCutoff] = useState<number>(Number.POSITIVE_INFINITY);
  const [playing, setPlaying] = useState(false);

  // Build the graph once per data set.
  useEffect(() => {
    if (!box.current) return;
    const els: ElementDefinition[] = [
      ...data.nodes.map((n) => ({
        data: { ...n, color: (NODE_STYLE[n.type] ?? NODE_STYLE.entity!).color, shape: (NODE_STYLE[n.type] ?? NODE_STYLE.entity!).shape,
          size: n.role === "member" ? 18 + n.risk * 18 : 14 },
        classes: [n.suspicious ? "suspicious" : "", n.derived ? "derived" : "", n.role].join(" "),
      })),
      ...data.edges.map((e) => ({
        data: { ...e, t: e.ts ? new Date(e.ts).getTime() : 0 },
        classes: [e.suspicious ? "suspicious" : "", e.type === "TRANSFERS_TO" ? "transfer" : "link"].join(" "),
      })),
    ];
    const inst = cytoscape({
      container: box.current,
      elements: els,
      wheelSensitivity: 0.2,
      style: [
        { selector: "node", style: { "background-color": "data(color)", shape: "data(shape)" as never, width: "data(size)", height: "data(size)",
          label: "data(label)", color: VIZ.text, "font-size": 8, "text-valign": "bottom", "text-margin-y": 3, "border-width": 2, "border-color": VIZ.surface } },
        { selector: "node.suspicious", style: { "border-color": "#DC2626", "border-width": 3 } },
        { selector: "node.derived", style: { "border-style": "dashed" } },
        { selector: "node.related", style: { opacity: 0.85 } },
        { selector: "node:selected", style: { "border-color": "#172554", "border-width": 3 } },
        { selector: "edge", style: { width: 1, "line-color": VIZ.neutral, "curve-style": "bezier", opacity: 0.55 } },
        { selector: "edge.transfer", style: { "target-arrow-shape": "triangle", "target-arrow-color": VIZ.neutral, "arrow-scale": 0.6 } },
        { selector: "edge.link", style: { "line-style": "dashed" } },
        { selector: "edge.suspicious", style: { width: 2, "line-color": VIZ.contrast, "target-arrow-color": VIZ.contrast, opacity: 0.95 } },
        { selector: ".faded", style: { display: "none" } },
      ],
      layout: { name: "fcose", animate: false, randomize: true, nodeRepulsion: 8000, idealEdgeLength: 70 } as never,
    });
    // Cytoscape only listens to window resizes; follow the panel (chat docking, panel drag) as well.
    const ro = new ResizeObserver(() => { inst.resize(); });
    ro.observe(box.current);
    inst.on("tap", "node", (evt) => setSelected(evt.target.data() as GraphNode));
    inst.on("tap", (evt) => evt.target === inst && setSelected(null));
    cy.current = inst;
    return () => { ro.disconnect(); inst.destroy(); };
  }, [data]);

  // Type filters + time slider.
  useEffect(() => {
    const inst = cy.current;
    if (!inst) return;
    inst.batch(() => {
      inst.nodes().forEach((n) => { n.toggleClass("faded", hidden.has(n.data("type"))); });
      inst.edges().forEach((e) => {
        const t = e.data("t") as number;
        e.toggleClass("faded", (t > 0 && t > cutoff) || e.source().hasClass("faded") || e.target().hasClass("faded"));
      });
    });
  }, [hidden, cutoff, data]);

  // Expand neighbours: add the one-hop neighbourhood of the selected node (context, not case members).
  useEffect(() => {
    const inst = cy.current;
    const nb = neighbors.data as { nodes: { id: string; type?: string }[]; edges: { source: string; target: string; type: string }[] } | undefined;
    if (!inst || !nb) return;
    const add: ElementDefinition[] = [];
    nb.nodes.forEach((n) => {
      if (inst.getElementById(n.id).empty()) {
        const st = NODE_STYLE[n.type ?? "entity"] ?? NODE_STYLE.entity!;
        add.push({ data: { id: n.id, type: n.type ?? "entity", label: n.id.split(":").slice(1).join(":"), color: st.color, shape: st.shape, size: 10, role: "context", risk: 0, evidence_ids: [] }, classes: "context" });
      }
    });
    nb.edges.forEach((e, i) => {
      add.push({ data: { id: `nb:${expand}:${i}`, source: e.source, target: e.target, type: e.type, t: 0 }, classes: "link" });
    });
    inst.add(add);
    inst.layout({ name: "fcose", animate: true, randomize: false } as never).run();
  }, [neighbors.data, expand]);

  // Replay animation through the transaction timeline.
  useEffect(() => {
    if (!playing || !times.length) return;
    let i = 0;
    const step = Math.max(1, Math.floor(times.length / 60));
    setCutoff(times[0]!);
    const id = setInterval(() => {
      i += step;
      if (i >= times.length) {
        setCutoff(Number.POSITIVE_INFINITY);
        setPlaying(false);
      } else setCutoff(times[i]!);
    }, 120);
    return () => clearInterval(id);
  }, [playing, times]);

  const sliderMax = times.length;
  const sliderVal = cutoff === Number.POSITIVE_INFINITY ? sliderMax : Math.max(0, times.findIndex((t) => t > cutoff));

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-1.5 border-b border-line px-3 py-2 text-xs">
        {types.map((t) => {
          const st = NODE_STYLE[t] ?? NODE_STYLE.entity!;
          const on = !hidden.has(t);
          return (
            <button key={t} type="button" aria-pressed={on}
              onClick={() => setHidden((h) => { const n = new Set(h); if (n.has(t)) n.delete(t); else n.add(t); return n; })}
              className={`flex items-center gap-1 rounded border px-1.5 py-0.5 ${on ? "border-line" : "border-transparent opacity-40"} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400`}>
              <span className="h-2 w-2 rounded-full" style={{ background: st.color }} aria-hidden="true" /> {humanize(t)}
            </button>
          );
        })}
        <span className="ml-auto flex items-center gap-3 text-muted">
          <span className="flex items-center gap-1"><span className="h-0.5 w-4" style={{ background: VIZ.contrast }} /> cited in evidence</span>
          <span className="flex items-center gap-1"><span className="h-0.5 w-4" style={{ background: VIZ.neutral }} /> other</span>
        </span>
        <Button variant="ghost" className="px-1.5 py-0.5" aria-label="Fit graph" onClick={() => cy.current?.fit(undefined, 20)}><Maximize2 className="h-3.5 w-3.5" /></Button>
      </div>
      <div className="relative min-h-0 flex-1">
        <div ref={box} className="absolute inset-0" role="img" aria-label={`Network graph with ${data.nodes.length} entities and ${data.edges.length} links`} />
        {data.truncated && <p className="absolute left-2 top-2 rounded bg-amber-500/20 px-2 py-1 text-[11px] text-amber-200">Showing the first 2,000 transactions (cited ones first)</p>}
        {selected && (
          <div className="absolute right-2 top-2 w-72 rounded-lg border border-line bg-panel/95 p-3 text-xs shadow-xl">
            <div className="mb-1 flex items-center gap-2">
              <span className="font-mono text-sm text-slate-100">{selected.label}</span>
              <Badge>{humanize(selected.type)}</Badge>
              {selected.derived && <Badge tone="amber">derived</Badge>}
            </div>
            <p className="text-muted">{selected.role === "member" ? "Network member" : selected.role === "related" ? "Related entity" : "Context (expanded neighbour)"}{selected.suspicious ? " · cited in risk evidence" : ""}</p>
            {selected.role !== "context" && <p className="mt-1">Highest evidence strength: <span className="font-mono">{num(selected.risk)}</span></p>}
            <div className="mt-2"><EvidenceChips caseId={caseId} ids={selected.evidence_ids ?? []} /></div>
            <Button className="mt-2 w-full" onClick={() => setExpand(selected.id)} disabled={neighbors.isFetching}>
              {neighbors.isFetching && expand === selected.id ? "Loading…" : "Expand neighbours"}
            </Button>
          </div>
        )}
      </div>
      {times.length > 0 && (
        <div className="flex items-center gap-3 border-t border-line px-3 py-2 text-xs">
          <Button variant="ghost" className="px-1.5 py-0.5" aria-label={playing ? "Pause replay" : "Replay money movement"} onClick={() => setPlaying((p) => !p)}>
            {playing ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
          </Button>
          <input type="range" min={0} max={sliderMax} value={sliderVal} aria-label="Transaction time cutoff" className="flex-1 accent-sky-500"
            onChange={(e) => { const i = Number(e.target.value); setCutoff(i >= sliderMax ? Number.POSITIVE_INFINITY : times[i]!); }} />
          <span className="w-44 text-right font-mono text-muted">{cutoff === Number.POSITIVE_INFINITY ? "all transactions" : ts(new Date(cutoff).toISOString())}</span>
        </div>
      )}
    </div>
  );
}
