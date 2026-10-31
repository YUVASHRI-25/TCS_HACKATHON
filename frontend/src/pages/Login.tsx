import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { api, unwrap } from "@/api/client";
import { useAuth } from "@/store/auth";
import { Button, ErrorState } from "@/components/ui/primitives";
import { GuardrailBanner } from "@/components/layout/Shell";

export function LoginPage() {
  const signIn = useAuth((s) => s.signIn);
  const setup = useQuery({ queryKey: ["setup"], queryFn: async () => unwrap(await api.GET("/api/auth/setup")) });
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const firstRun = setup.data?.needs_setup === true;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (firstRun) unwrap(await api.POST("/api/auth/setup", { body: { username, display_name: displayName, password } }));
      const r = unwrap(await api.POST("/api/auth/login", { body: { username, password } }));
      signIn(r.token, r.user);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <GuardrailBanner />
      <div className="flex flex-1 items-center justify-center p-6">
        <form className="w-full max-w-sm space-y-4 rounded-lg border border-line bg-panel p-6"
          onSubmit={(e) => { e.preventDefault(); void submit(); }}>
          <div className="flex items-center gap-2">
            <Activity className="h-6 w-6 text-sky-400" aria-hidden="true" />
            <div>
              <h1 className="text-lg font-bold tracking-widest">TRACE</h1>
              <p className="text-xs text-muted">Financial crime network investigation</p>
            </div>
          </div>
          {firstRun && (
            <p className="rounded border border-sky-500/30 bg-sky-500/10 p-2 text-xs text-sky-200">
              First run: create the administrator account. There is no default account or password.
            </p>
          )}
          <label className="block text-sm">
            <span className="text-muted">Username</span>
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required
              className="mt-1 w-full rounded border border-line bg-canvas px-2 py-1.5" />
          </label>
          {firstRun && (
            <label className="block text-sm">
              <span className="text-muted">Display name</span>
              <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} className="mt-1 w-full rounded border border-line bg-canvas px-2 py-1.5" />
            </label>
          )}
          <label className="block text-sm">
            <span className="text-muted">Password{firstRun ? " (at least 8 characters)" : ""}</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
              autoComplete={firstRun ? "new-password" : "current-password"} minLength={firstRun ? 8 : undefined}
              className="mt-1 w-full rounded border border-line bg-canvas px-2 py-1.5" />
          </label>
          {error !== null && <ErrorState error={error} />}
          <Button type="submit" variant="primary" className="w-full" disabled={busy || setup.isLoading}>
            {firstRun ? "Create administrator and sign in" : "Sign in"}
          </Button>
        </form>
      </div>
    </div>
  );
}
