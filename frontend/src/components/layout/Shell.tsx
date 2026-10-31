import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { Activity, BarChart3, Database, FolderSearch, LayoutDashboard, ListChecks, LogOut, Network, Radio, Search, Settings2, ShieldAlert, Users } from "lucide-react";
import { api } from "@/api/client";
import { useAuth } from "@/store/auth";
import { cn } from "@/lib/format";
import { useUi } from "@/store/ui";
import { useHealth } from "@/hooks/useApi";
import { CommandPalette } from "./CommandPalette";
import { EvidenceDrawer } from "@/components/evidence/EvidenceDrawer";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/cases", label: "Cases", icon: FolderSearch },
  { to: "/explorer", label: "Network Explorer", icon: Network },
  { to: "/datasets", label: "Datasets & Runs", icon: Database },
  { to: "/metrics", label: "Metrics", icon: BarChart3 },
  { to: "/live", label: "Live Stream", icon: Radio },
];
const ADMIN_NAV = [
  { to: "/admin/system", label: "System health", icon: Activity },
  { to: "/admin/users", label: "Users", icon: Users },
  { to: "/admin/settings", label: "Detection settings", icon: Settings2 },
  { to: "/admin/activity", label: "Activity log", icon: ListChecks },
];

export function GuardrailBanner() {
  return (
    <div role="note" className="flex items-center gap-2 border-b border-amber-500/30 bg-amber-500/10 px-4 py-1.5 text-xs text-amber-200">
      <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
      Decision support only. A human investigator makes the final decision.
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const setPalette = useUi((s) => s.setPalette);
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const health = useHealth();
  const user = useAuth((s) => s.user);
  const signOut = useAuth((s) => s.signOut);
  const navLink = ({ isActive }: { isActive: boolean }) =>
    cn(
      "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400",
      isActive ? "bg-sky-500/15 text-sky-200" : "text-slate-300 hover:bg-slate-700/40",
    );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setPalette]);

  return (
    <div className="flex h-full flex-col">
      <GuardrailBanner />
      <div className="flex min-h-0 flex-1">
        <nav aria-label="Primary" className="flex w-56 shrink-0 flex-col border-r border-line bg-panel2">
          <div className="flex items-center gap-2 px-4 py-4">
            <Activity className="h-5 w-5 text-sky-400" aria-hidden="true" />
            <div>
              <p className="text-sm font-bold tracking-widest text-slate-100">TRACE</p>
              <p className="text-[10px] leading-tight text-muted">Transaction Relationship Analysis &amp; Crime Exploration</p>
            </div>
          </div>
          <ul className="flex-1 space-y-0.5 px-2">
            {NAV.map(({ to, label, icon: Icon }) => (
              <li key={to}>
                <NavLink to={to} end={to === "/"} className={navLink}>
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {label}
                </NavLink>
              </li>
            ))}
            {user?.role === "admin" && (
              <>
                <li className="px-3 pb-1 pt-4 text-[10px] uppercase tracking-wider text-muted">Administration</li>
                {ADMIN_NAV.map(({ to, label, icon: Icon }) => (
                  <li key={to}>
                    <NavLink to={to} className={navLink}>
                      <Icon className="h-4 w-4" aria-hidden="true" />
                      {label}
                    </NavLink>
                  </li>
                ))}
              </>
            )}
          </ul>
          {user && (
            <div className="flex items-center justify-between border-t border-line px-4 py-3 text-xs">
              <div className="min-w-0">
                <p className="truncate text-slate-200">{user.display_name}</p>
                <p className="text-muted">{user.role === "admin" ? "Administrator" : "Investigator"}</p>
              </div>
              <button type="button" aria-label="Sign out" title="Sign out"
                onClick={() => { void api.POST("/api/auth/logout"); signOut(); }}
                className="rounded p-1.5 text-muted hover:bg-slate-700/50 hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400">
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          )}
          <div className="border-t border-line px-4 py-3 text-[11px] text-muted">
            <p>
              API:{" "}
              {health.isError ? (
                <span className="text-red-300">unreachable</span>
              ) : health.data ? (
                <span className="text-emerald-300">connected</span>
              ) : (
                "…"
              )}
            </p>
            {health.data && (
              <p>
                LLM: <span className="font-mono">{health.data.llm_provider}</span> · graph:{" "}
                <span className="font-mono">{health.data.graph_backend}</span>
              </p>
            )}
          </div>
        </nav>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center gap-3 border-b border-line bg-panel/60 px-4 py-2">
            <form
              role="search"
              className="flex flex-1 items-center gap-2 rounded-md border border-line bg-canvas px-3 py-1.5"
              onSubmit={(e) => {
                e.preventDefault();
                if (q.trim()) navigate(`/cases?q=${encodeURIComponent(q.trim())}`);
              }}
            >
              <Search className="h-4 w-4 text-muted" aria-hidden="true" />
              <input
                aria-label="Search cases"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search cases by id or summary…"
                className="w-full bg-transparent text-sm outline-none placeholder:text-muted"
              />
            </form>
            <button
              type="button"
              onClick={() => setPalette(true)}
              className="rounded-md border border-line px-2 py-1 text-xs text-muted hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
            >
              Ctrl K
            </button>
          </header>
          <main className="min-h-0 flex-1 overflow-auto">{children}</main>
        </div>
      </div>
      <CommandPalette />
      <EvidenceDrawer />
    </div>
  );
}
