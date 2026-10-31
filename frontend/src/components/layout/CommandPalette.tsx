import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useUi } from "@/store/ui";
import { useCases, useEntitySearch } from "@/hooks/useApi";
import { TierBadge } from "@/components/ui/primitives";

const PAGES = [
  { label: "Go to Dashboard", to: "/" },
  { label: "Go to Cases", to: "/cases" },
  { label: "Go to Network Explorer", to: "/explorer" },
  { label: "Go to Metrics", to: "/metrics" },
  { label: "Go to Live Stream", to: "/live" },
];

export function CommandPalette() {
  const open = useUi((s) => s.paletteOpen);
  const setOpen = useUi((s) => s.setPalette);
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const cases = useCases({ q: q || undefined });
  const entities = useEntitySearch(q);

  useEffect(() => {
    if (open) {
      setQ("");
      setIdx(0);
      setTimeout(() => input.current?.focus(), 0);
    }
  }, [open]);

  const items = useMemo(() => {
    const ql = q.toLowerCase();
    const pages = PAGES.filter((p) => p.label.toLowerCase().includes(ql)).map((p) => ({ key: p.to, label: p.label, to: p.to, kind: "page" as const }));
    const cs = (cases.data ?? []).slice(0, 8).map((c) => ({ key: c.id, label: `${c.id} — ${c.summary}`, to: `/cases/${c.id}`, kind: "case" as const, tier: c.tier }));
    const es = (entities.data ?? []).slice(0, 8).map((e) => ({ key: e.id, label: e.id, to: `/explorer?node=${encodeURIComponent(e.id)}`, kind: "entity" as const }));
    return [...pages, ...cs, ...es];
  }, [q, cases.data, entities.data]);

  if (!open) return null;
  const go = (to: string) => {
    setOpen(false);
    navigate(to);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-24" onClick={() => setOpen(false)}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="w-full max-w-xl overflow-hidden rounded-lg border border-line bg-panel shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          ref={input}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setIdx(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
            if (e.key === "ArrowDown") setIdx((i) => Math.min(i + 1, items.length - 1));
            if (e.key === "ArrowUp") setIdx((i) => Math.max(i - 1, 0));
            if (e.key === "Enter" && items[idx]) go(items[idx].to);
          }}
          aria-label="Search pages, cases and entities"
          placeholder="Jump to a page, case or entity…"
          className="w-full border-b border-line bg-transparent px-4 py-3 text-sm outline-none placeholder:text-muted"
        />
        <ul className="max-h-80 overflow-auto py-1" role="listbox">
          {items.length === 0 && <li className="px-4 py-3 text-xs text-muted">No matches</li>}
          {items.map((it, i) => (
            <li
              key={`${it.kind}:${it.key}`}
              role="option"
              aria-selected={i === idx}
              onMouseEnter={() => setIdx(i)}
              onClick={() => go(it.to)}
              className={`flex cursor-pointer items-center gap-2 px-4 py-2 text-sm ${i === idx ? "bg-sky-500/15" : ""}`}
            >
              <span className="w-12 text-[10px] uppercase text-muted">{it.kind}</span>
              {"tier" in it && it.tier && <TierBadge tier={it.tier} />}
              <span className="truncate">{it.label}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
