import { useEffect, useRef, useState } from "react";
import { AlertCircle, ArrowUp, ChevronDown, MessageSquarePlus, ShieldCheck, Sparkles, X } from "lucide-react";
import type { CaseOut, ChatAnswer, ChatMessage } from "@/api/client";
import { useChat, useClearChat, useSendChat } from "@/hooks/useApi";
import { useUi } from "@/store/ui";
import { EvidenceChips } from "@/components/evidence/EvidenceChip";
import { cn } from "@/lib/format";

const FIRST_QUESTION = "Why is this network suspicious?";
const SUGGESTIONS = [
  "What could be an innocent explanation?",
  "Which accounts share a device or IP?",
  "What should I check next?",
  "Summarise this case for my report",
];
const THINKING = ["Reading the evidence…", "Checking the links between accounts…", "Weighing innocent explanations…", "Writing a plain-language answer…"];

const isEvidenceId = (x: string) => /^E\d+$/.test(x);

function Details({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <details className="group rounded-lg border border-line bg-panel2/60 px-3 py-2 text-sm">
      <summary className="flex cursor-pointer list-none items-center justify-between font-medium text-slate-300">
        {title}
        <ChevronDown className="h-4 w-4 text-muted transition-transform group-open:rotate-180" aria-hidden="true" />
      </summary>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-300">{items.map((x, i) => <li key={i}>{x}</li>)}</ul>
    </details>
  );
}

function AnswerView({ caseId, a, onAsk }: { caseId: string; a: ChatAnswer; onAsk: (q: string) => void }) {
  const claims = a.claims.filter((c) => c.text.trim());
  return (
    <div className="space-y-3">
      <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-slate-100">{a.answer}</p>
      {claims.length > 0 && (
        <div>
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">Key reasons</p>
          <ul className="space-y-2">
            {claims.map((c, i) => {
              const ev = c.evidence_ids.filter(isEvidenceId);
              const rec = [...c.evidence_ids.filter((x) => !isEvidenceId(x)), ...c.record_ids].slice(0, 3);
              return (
                <li key={i} className="rounded-lg border border-line bg-panel p-2.5 text-sm text-slate-300">
                  {c.text}
                  <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    {ev.length > 0 && <EvidenceChips caseId={caseId} ids={ev} />}
                    {rec.map((r) => <span key={r} className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">{r}</span>)}
                    {!c.cited && <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">not backed by evidence</span>}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      <Details title="Could this be innocent?" items={[...a.legitimate_explanations, ...a.contradictory_evidence]} />
      <Details title="What the data can't tell us" items={a.data_limitations} />
      {a.suggested_next_steps.length > 0 && (
        <div>
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">Check next</p>
          <ul className="space-y-1 text-sm text-slate-300">
            {a.suggested_next_steps.map((s, i) => <li key={i} className="flex gap-2"><span className="text-sky-400" aria-hidden="true">→</span>{s}</li>)}
          </ul>
        </div>
      )}
      {a.rejected_citations.length > 0 && (
        <p className="flex items-start gap-1.5 text-xs text-amber-300"><AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {a.rejected_citations.length} reference(s) the AI made up were removed — only evidence from this case is shown.</p>
      )}
      <div className="flex flex-wrap gap-1.5 pt-1">
        {SUGGESTIONS.slice(0, 3).map((q) => (
          <button key={q} type="button" onClick={() => onAsk(q)}
            className="rounded-full border border-line bg-panel px-3 py-1 text-xs text-slate-300 transition-colors hover:border-sky-400 hover:text-sky-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400">{q}</button>
        ))}
      </div>
      <p className="flex items-center gap-1.5 text-[11px] text-muted"><ShieldCheck className="h-3 w-3" aria-hidden="true" />
        AI explanation of this case's evidence{a.model ? ` (${a.model})` : ""}. A human investigator makes the decision.</p>
    </div>
  );
}

function Bubble({ m, caseId, onAsk }: { m: ChatMessage; caseId: string; onAsk: (q: string) => void }) {
  if (m.role === "user")
    return <div className="flex justify-end"><p className="max-w-[85%] rounded-2xl rounded-br-md bg-sky-600 px-3.5 py-2 text-sm text-white shadow-sm">{m.text}</p></div>;
  return (
    <div className="flex gap-2.5" data-role="assistant">
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-violet-500/15 text-violet-400"><Sparkles className="h-4 w-4" aria-hidden="true" /></span>
      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-md border border-line bg-panel p-3.5 shadow-sm">
        {m.answer && <AnswerView caseId={caseId} a={m.answer} onAsk={onAsk} />}
      </div>
    </div>
  );
}

function Thinking() {
  const [i, setI] = useState(0);
  useEffect(() => { const t = setInterval(() => setI((x) => (x + 1) % THINKING.length), 2500); return () => clearInterval(t); }, []);
  return (
    <div className="flex gap-2.5" role="status" aria-live="polite">
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-violet-500/15 text-violet-400"><Sparkles className="h-4 w-4 animate-pulse" aria-hidden="true" /></span>
      <div className="rounded-2xl rounded-tl-md border border-line bg-panel px-3.5 py-3 text-sm text-muted shadow-sm">
        <span className="mr-2 inline-flex gap-1" aria-hidden="true">
          {[0, 150, 300].map((d) => <span key={d} className="h-1.5 w-1.5 animate-bounce rounded-full bg-violet-400" style={{ animationDelay: `${d}ms` }} />)}
        </span>
        {THINKING[i]}
      </div>
    </div>
  );
}

/** "Explain with AI": a docked chat that answers from this case's evidence only and remembers the conversation. */
export function ChatDrawer({ c, docked }: { c: CaseOut; docked: boolean }) {
  const open = useUi((s) => s.chatCase === c.id);
  const close = useUi((s) => s.closeChat);
  const history = useChat(c.id, open);
  const send = useSendChat(c.id);
  const clear = useClearChat(c.id);
  const [text, setText] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [failed, setFailed] = useState<{ q: string; msg: string } | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const autoAsked = useRef<string | null>(null);

  const ask = (q: string) => {
    const question = q.trim();
    if (question.length < 2 || send.isPending) return;
    setPending(question);
    setFailed(null);
    setText("");
    send.mutate(question, {
      onError: (e) => setFailed({ q: question, msg: e instanceof Error ? e.message : String(e) }),
      onSettled: () => setPending(null),
    });
  };

  // First open on a case with no conversation: answer the headline question straight away.
  useEffect(() => {
    if (!open || !history.data || autoAsked.current === c.id) return;
    autoAsked.current = c.id;
    if (history.data.messages.length === 0 && history.data.llm_configured) ask(FIRST_QUESTION);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, history.data, c.id]);

  // Scroll only the chat itself (never the page): stay at the bottom while waiting, and show a new answer from
  // its first line rather than its last.
  useEffect(() => {
    const box = scroller.current;
    if (!box) return;
    if (pending || failed) { box.scrollTo({ top: box.scrollHeight, behavior: "smooth" }); return; }
    const answers = box.querySelectorAll<HTMLElement>('[data-role="assistant"]');
    const last = answers[answers.length - 1];
    if (last) box.scrollTo({ top: Math.max(0, last.offsetTop - 12), behavior: "smooth" });
  }, [history.data?.messages.length, pending, failed]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && open && !useUi.getState().evidence) close(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  const messages = history.data?.messages ?? [];
  const configured = history.data?.llm_configured ?? true;
  return (
    <aside role="dialog" aria-label="Explain with AI" aria-hidden={!open}
      style={docked ? { width: open ? "28rem" : 0 } : undefined}
      className={cn("flex flex-col overflow-hidden bg-canvas",
        !open && "invisible",   // closed: out of the tab order and the accessibility tree once the slide ends
        docked
          ? "relative shrink-0 border-l border-line transition-[width,visibility] duration-300 ease-out"
          : cn("fixed inset-y-0 right-0 z-30 w-full max-w-[28rem] border-l border-line shadow-2xl transition-[transform,visibility] duration-300 ease-out",
              open ? "translate-x-0" : "pointer-events-none translate-x-full"))}>
      <div className={cn("flex h-full min-h-0 flex-col", docked && "w-[28rem]")}>
      <header className="flex items-center gap-3 border-b border-line bg-panel px-4 py-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-sky-500 text-white shadow-sm"><Sparkles className="h-5 w-5" aria-hidden="true" /></span>
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold text-slate-100">Explain with AI</h2>
          <p className="truncate text-xs text-muted">Case {c.id} · answers only from this case's evidence</p>
        </div>
        <button type="button" onClick={() => { autoAsked.current = null; clear.mutate(undefined, { onSuccess: () => { autoAsked.current = c.id; ask(FIRST_QUESTION); } }); }}
          disabled={clear.isPending || send.isPending || messages.length === 0} title="Start a new conversation" aria-label="Start a new conversation"
          className="rounded-lg p-2 text-muted transition-colors hover:bg-slate-700/40 hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 disabled:opacity-40"><MessageSquarePlus className="h-4 w-4" /></button>
        <button type="button" onClick={close} aria-label="Close chat"
          className="rounded-lg p-2 text-muted transition-colors hover:bg-slate-700/40 hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400"><X className="h-4 w-4" /></button>
      </header>

      <div ref={scroller} className="relative min-h-0 flex-1 space-y-4 overflow-y-auto bg-panel2/50 px-4 py-4" aria-live="polite">
        {history.isLoading && <p className="text-sm text-muted">Loading conversation…</p>}
        {history.isError && <p role="alert" className="text-sm text-red-300">Could not load the conversation.</p>}
        {!configured && (
          <div role="alert" className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
            The AI service is not set up. Add a Gemini API key (<code>GEMINI_API_KEY</code>) to the server settings to enable explanations.
          </div>
        )}
        {configured && messages.length === 0 && !pending && !failed && !history.isLoading && (
          <p className="text-sm text-muted">Ask anything about this case — I'll explain it using only the evidence we hold.</p>
        )}
        {messages.map((m) => <Bubble key={m.id} m={m} caseId={c.id} onAsk={ask} />)}
        {pending && <div className="flex justify-end"><p className="max-w-[85%] rounded-2xl rounded-br-md bg-sky-600 px-3.5 py-2 text-sm text-white shadow-sm">{pending}</p></div>}
        {pending && <Thinking />}
        {failed && (
          <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
            <p className="font-medium">Couldn't get an answer</p>
            <p className="mt-0.5 text-xs text-red-300/80">{failed.msg}</p>
            <button type="button" onClick={() => ask(failed.q)} className="mt-2 rounded-lg border border-red-400/40 px-3 py-1 text-xs font-medium hover:bg-red-500/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400">Try again</button>
          </div>
        )}
      </div>

      <footer className="border-t border-line bg-panel p-3">
        {messages.length === 0 && !pending && configured && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {[FIRST_QUESTION, ...SUGGESTIONS].map((q) => (
              <button key={q} type="button" onClick={() => ask(q)} className="rounded-full border border-line px-3 py-1 text-xs text-slate-300 transition-colors hover:border-sky-400 hover:text-sky-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400">{q}</button>
            ))}
          </div>
        )}
        <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); ask(text); }}>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={1} aria-label="Your question" maxLength={1000}
            placeholder={configured ? "Ask a follow-up…" : "AI service not set up"} disabled={!configured}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(text); } }}
            className="max-h-32 min-h-[2.5rem] flex-1 resize-none rounded-xl border border-line bg-canvas px-3 py-2 text-sm outline-none transition-colors focus:border-sky-400 focus:ring-2 focus:ring-sky-400/30 disabled:opacity-60" />
          <button type="submit" disabled={!configured || send.isPending || text.trim().length < 2} aria-label="Send question"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-sky-600 text-white transition-colors hover:bg-sky-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 disabled:cursor-not-allowed disabled:opacity-40"><ArrowUp className="h-5 w-5" /></button>
        </form>
        <p className="mt-1.5 text-center text-[11px] text-muted">Enter to send · Shift+Enter for a new line · Esc to close</p>
      </footer>
      </div>
    </aside>
  );
}
