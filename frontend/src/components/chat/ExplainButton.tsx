import { Sparkles } from "lucide-react";
import { useUi } from "@/store/ui";
import { cn } from "@/lib/format";

/** The entry point to the AI chat. `prominent` is the large call-to-action used inside the case overview. */
export function ExplainButton({ caseId, prominent = false }: { caseId: string; prominent?: boolean }) {
  const open = useUi((s) => s.openChat);
  const active = useUi((s) => s.chatCase === caseId);
  return (
    <button type="button" onClick={() => open(caseId)} aria-expanded={active} aria-label="Explain this case with AI"
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl font-medium text-white shadow-sm transition-all",
        "bg-gradient-to-r from-violet-500 to-sky-500 hover:shadow-md hover:brightness-105 active:scale-[0.98]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 focus-visible:ring-offset-2",
        prominent ? "px-4 py-2.5 text-sm" : "px-3 py-1.5 text-sm",
      )}>
      <Sparkles className="h-4 w-4" aria-hidden="true" />
      Explain with AI
    </button>
  );
}
