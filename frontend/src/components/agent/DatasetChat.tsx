import { useEffect, useRef, useState } from "react";
import { MessageSquare, Send, X } from "lucide-react";
import { ApiError, jsonCall } from "@/api/client";

interface Answer {
  answer: string; findings: { text: string; refs: string[] }[]; data_limitations: string[];
  suggested_next_steps: string[]; rejected_refs: string[]; model: string;
}
type Msg = { role: "user" | "assistant" | "error"; text: string; a?: Answer };

const QUICK = ["Summarize this dataset", "Any data quality problems?", "Is it suitable for network analysis?", "What should I check before running analysis?"];

/** Mini chat about one uploaded dataset. Every answer comes from the backend LLM over a profile of the real file. */
export function DatasetChat({ datasetId, name, autoAsk, onClose }: { datasetId: number; name: string; autoAsk: boolean; onClose: () => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const started = useRef<number | null>(null);

  const send = async (question: string, prior: Msg[]) => {
    const next: Msg[] = [...prior, { role: "user", text: question }];
    setMsgs(next);
    setBusy(true);
    try {
      const history = prior.filter((m) => m.role !== "error").map((m) => ({ role: m.role, content: m.text }));
      const a = await jsonCall<Answer>("POST", `/api/datasets/${datasetId}/chat`, { question, history });
      setMsgs([...next, { role: "assistant", text: a.answer, a }]);
    } catch (e) {
      setMsgs([...next, { role: "error", text: e instanceof ApiError ? e.message : String(e) }]);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (started.current === datasetId) return;
    started.current = datasetId;
    setMsgs([]);
    if (autoAsk) void send("Summarize this dataset and what it can or cannot support for a financial-crime investigation.", []);
  }, [datasetId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [msgs, busy]);

  return (
    <div className="fixed bottom-4 right-4 z-40 flex h-[32rem] w-[24rem] max-w-[calc(100vw-2rem)] flex-col rounded-xl border border-line bg-panel shadow-xl" role="dialog" aria-label="Dataset assistant">
      <header className="flex items-center gap-2 border-b border-line px-3 py-2">
        <MessageSquare className="h-4 w-4 text-sky-400" aria-hidden="true" />
        <div className="min-w-0 flex-1"><p className="text-sm font-semibold">Dataset assistant</p><p className="truncate text-[11px] text-muted">#{datasetId} · {name}</p></div>
        <button type="button" onClick={onClose} aria-label="Close chat" className="rounded p-1 text-muted hover:bg-slate-700/50"><X className="h-4 w-4" /></button>
      </header>
      <div className="min-h-0 flex-1 space-y-3 overflow-auto p-3 text-sm">
        {msgs.length === 0 && !busy && <p className="text-xs text-muted">Ask the AI about this upload. Answers are generated from a profile computed from the file's real rows.</p>}
        {msgs.map((m, i) => m.role === "user" ? (
          <div key={i} className="ml-8 rounded-lg bg-sky-500/15 px-3 py-2 text-slate-100">{m.text}</div>
        ) : m.role === "error" ? (
          <div key={i} className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{m.text}</div>
        ) : (
          <div key={i} className="mr-4 space-y-2 rounded-lg border border-line bg-panel2 px-3 py-2">
            <p className="whitespace-pre-wrap leading-relaxed">{m.text}</p>
            {m.a && m.a.findings.length > 0 && <ul className="list-disc space-y-1 pl-4 text-xs">{m.a.findings.map((f, j) => <li key={j}>{f.text} {f.refs.map((r) => <code key={r} className="mx-0.5 rounded bg-slate-800 px-1 text-[10px]">{r}</code>)}</li>)}</ul>}
            {m.a && m.a.data_limitations.length > 0 && <div className="text-xs"><b className="text-amber-300">Limitations</b><ul className="list-disc pl-4">{m.a.data_limitations.map((x, j) => <li key={j}>{x}</li>)}</ul></div>}
            {m.a && m.a.suggested_next_steps.length > 0 && <div className="text-xs"><b>Next steps</b><ul className="list-disc pl-4">{m.a.suggested_next_steps.map((x, j) => <li key={j}>{x}</li>)}</ul></div>}
            {m.a && <p className="text-[10px] text-muted">{m.a.model} · decision support only</p>}
          </div>
        ))}
        {busy && <p className="text-xs text-muted">Reasoning over the dataset…</p>}
        <div ref={end} />
      </div>
      <div className="border-t border-line p-2">
        <div className="mb-1.5 flex flex-wrap gap-1">{QUICK.map((s) => <button key={s} type="button" disabled={busy} onClick={() => void send(s, msgs)} className="rounded-full border border-line px-2 py-0.5 text-[11px] hover:bg-sky-500/10 disabled:opacity-50">{s}</button>)}</div>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); const t = q.trim(); if (t.length >= 2 && !busy) { setQ(""); void send(t, msgs); } }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about this dataset…" aria-label="Message" className="min-w-0 flex-1 rounded border border-line bg-canvas px-2 py-1.5 text-sm" />
          <button type="submit" disabled={busy || q.trim().length < 2} aria-label="Send" className="rounded bg-sky-600 px-2.5 text-white disabled:opacity-50"><Send className="h-4 w-4" /></button>
        </form>
      </div>
    </div>
  );
}
