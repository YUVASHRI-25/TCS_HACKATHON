import { useEffect, useState } from "react";
import { BadgeCheck, ShieldX } from "lucide-react";
import { useActivity, useAdminSettings, useCreateUser, useSaveSettings, useUpdateUser, useUsers, type EditableSettings } from "@/hooks/useApi";
import { useAuth } from "@/store/auth";
import { Badge, Button, Card, EmptyState, ErrorState, SkeletonRows } from "@/components/ui/primitives";
import { humanize, ts } from "@/lib/format";

// ------------------------------------------------------------------------------------------- users
export function UsersPage() {
  const users = useUsers();
  const create = useCreateUser();
  const upd = useUpdateUser();
  const me = useAuth((s) => s.user);
  const [form, setForm] = useState({ username: "", display_name: "", role: "investigator" as "investigator" | "admin", password: "" });

  return (
    <div className="space-y-5 p-6">
      <h1 className="text-lg font-semibold">Investigator accounts</h1>
      <Card title="Add an account">
        <form className="flex flex-wrap items-end gap-3 text-sm" onSubmit={(e) => { e.preventDefault(); create.mutate(form, { onSuccess: () => setForm({ ...form, username: "", display_name: "", password: "" }) }); }}>
          {(["username", "display_name"] as const).map((k) => (
            <label key={k}><span className="block text-xs text-muted">{humanize(k)}</span>
              <input value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} required={k === "username"}
                className="mt-1 w-44 rounded border border-line bg-canvas px-2 py-1.5" /></label>
          ))}
          <label><span className="block text-xs text-muted">Role</span>
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as "investigator" | "admin" })} className="mt-1 rounded border border-line bg-canvas px-2 py-1.5">
              <option value="investigator">Investigator</option><option value="admin">Administrator</option>
            </select></label>
          <label><span className="block text-xs text-muted">Initial password (8+ chars)</span>
            <input type="password" value={form.password} minLength={8} required autoComplete="new-password"
              onChange={(e) => setForm({ ...form, password: e.target.value })} className="mt-1 w-44 rounded border border-line bg-canvas px-2 py-1.5" /></label>
          <Button type="submit" variant="primary" disabled={create.isPending}>Create account</Button>
        </form>
        {create.isError && <div className="mt-2"><ErrorState error={create.error} /></div>}
      </Card>
      <Card title="Accounts">
        {users.isLoading && <SkeletonRows rows={3} />}
        {users.isError && <ErrorState error={users.error} />}
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted"><tr><th className="py-1 font-medium">User</th><th className="font-medium">Role</th><th className="font-medium">Status</th><th className="font-medium">Last sign-in</th><th /></tr></thead>
          <tbody>{(users.data ?? []).map((u) => (
            <tr key={u.id} className="border-t border-line">
              <td className="py-2">{u.display_name} <span className="font-mono text-xs text-muted">@{u.username}</span></td>
              <td>
                <select value={u.role} disabled={u.id === me?.id} aria-label={`Role of ${u.username}`}
                  onChange={(e) => upd.mutate({ id: u.id, role: e.target.value as "investigator" | "admin" })}
                  className="rounded border border-line bg-canvas px-1.5 py-0.5 text-xs">
                  <option value="investigator">Investigator</option><option value="admin">Administrator</option>
                </select>
              </td>
              <td>{u.active ? <Badge tone="green">active</Badge> : <Badge tone="red">deactivated</Badge>}</td>
              <td className="font-mono text-xs">{ts(u.last_login)}</td>
              <td className="text-right">
                {u.id !== me?.id && (
                  <Button className="py-0.5 text-xs" onClick={() => upd.mutate({ id: u.id, active: !u.active })}>
                    {u.active ? "Deactivate" : "Reactivate"}
                  </Button>
                )}
              </td>
            </tr>
          ))}</tbody>
        </table>
        {upd.isError && <ErrorState error={upd.error} />}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------------------- settings
function NumField({ label, value, onChange, hint }: { label: string; value: number; onChange: (v: number) => void; hint?: string }) {
  return (
    <label className="flex items-center justify-between gap-3 border-t border-line py-1.5 text-sm first:border-0">
      <span>{label}{hint && <span className="block text-[11px] text-muted">{hint}</span>}</span>
      <input type="number" step="any" min={0} value={value} onChange={(e) => onChange(Number(e.target.value))}
        className="w-24 rounded border border-line bg-canvas px-2 py-1 text-right font-mono" />
    </label>
  );
}

export function SettingsPage() {
  const q = useAdminSettings();
  const save = useSaveSettings();
  const [draft, setDraft] = useState<EditableSettings | null>(null);
  useEffect(() => { if (q.data) setDraft(structuredClone(q.data)); }, [q.data]);
  if (q.isLoading || !draft) return <div className="p-6"><SkeletonRows rows={10} /></div>;
  if (q.isError) return <div className="p-6"><ErrorState error={q.error} /></div>;

  type Sec = "case_rules" | "tiers" | "weights" | "ml_weights" | "penalties";
  const setSec = (sec: Sec, k: string, v: number) => setDraft({ ...draft, [sec]: { ...draft[sec], [k]: v } });
  const section = (sec: Sec, title: string, hint: string) => (
    <Card title={title}>
      <p className="mb-2 text-xs text-muted">{hint}</p>
      {Object.entries(draft[sec] ?? {}).map(([k, v]) => <NumField key={k} label={humanize(k)} value={v} onChange={(x) => setSec(sec, k, x)} />)}
    </Card>
  );

  return (
    <div className="space-y-5 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Detection settings</h1>
        <Button variant="primary" disabled={save.isPending} onClick={() => save.mutate(draft)}>Save settings</Button>
      </div>
      <p className="rounded border border-sky-500/30 bg-sky-500/10 p-2 text-xs text-sky-200">
        Thresholds are always computed from the data. Here you choose which percentile of each distribution is used, the
        analysis windows, signal weights and tier cut-offs. Changes are audited and take effect on the next analysis run.
      </p>
      {save.isError && <ErrorState error={save.error} />}
      {save.data && <p role="status" className="text-xs text-emerald-300">{save.data.note} {save.data.changes.map((c) => `${String(c.setting)}: ${String(c.from)} → ${String(c.to)}`).join("; ")}</p>}
      <div className="grid gap-5 lg:grid-cols-3">
        {section("tiers", "Tier cut-offs", "Priority score needed for HIGH / MEDIUM.")}
        {section("case_rules", "Case rules", "Two independent deterministic signal types are the default case rule; ML is capped.")}
        {section("weights", "Signal weights", "Points = weight × finding strength.")}
        {section("penalties", "Legitimate-explanation penalties", "Points removed = fit × weight.")}
        {section("ml_weights", "Model signal weights", "Combined model points are capped by the case rules.")}
      </div>
      <Card title="Detector thresholds and parameters">
        <div className="grid gap-x-8 md:grid-cols-2">
          {Object.entries(draft.detectors ?? {}).map(([det, spec]) => (
            <div key={det} className="py-2">
              <h3 className="mb-1 text-sm font-medium">{humanize(det)}</h3>
              {Object.entries(spec.derive ?? {}).map(([k, d]) => (
                <NumField key={k} label={`${humanize(k)} — percentile`} hint={`of ${humanize(d.metric ?? "")}`} value={d.percentile}
                  onChange={(x) => setDraft({ ...draft, detectors: { ...draft.detectors, [det]: { ...spec, derive: { ...spec.derive, [k]: { ...d, percentile: x } } } } })} />
              ))}
              {Object.entries(spec.params ?? {}).map(([k, v]) => (
                <NumField key={k} label={humanize(k)} value={v}
                  onChange={(x) => setDraft({ ...draft, detectors: { ...draft.detectors, [det]: { ...spec, params: { ...spec.params, [k]: x } } } })} />
              ))}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------------------- activity
export function ActivityPage() {
  const q = useActivity();
  if (q.isLoading) return <div className="p-6"><SkeletonRows rows={10} /></div>;
  if (q.isError) return <div className="p-6"><ErrorState error={q.error} /></div>;
  const a = q.data!;
  return (
    <div className="space-y-5 p-6">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold">System activity &amp; audit log</h1>
        {a.chain_valid ? <Badge tone="green"><BadgeCheck className="h-3 w-3" /> hash chain verified ({a.chain_entries} entries)</Badge>
          : <Badge tone="red"><ShieldX className="h-3 w-3" /> chain broken at #{a.broken_at_seq}</Badge>}
      </div>
      <Card>
        {a.entries.length === 0 ? <EmptyState title="No activity recorded yet" /> : (
          <table className="w-full text-xs">
            <thead className="text-left text-muted"><tr><th className="py-1 font-medium">#</th><th className="font-medium">Time</th><th className="font-medium">User</th><th className="font-medium">Action</th><th className="font-medium">Subject</th><th className="font-medium">Details</th></tr></thead>
            <tbody>{a.entries.map((e) => (
              <tr key={e.seq} className="border-t border-line align-top">
                <td className="py-1.5 font-mono text-muted">{e.seq}</td>
                <td className="whitespace-nowrap font-mono">{ts(e.ts)}</td>
                <td>{e.actor}</td>
                <td>{humanize(e.action)}</td>
                <td className="font-mono">{e.case_id === "SYSTEM" ? <Badge>system</Badge> : e.case_id}</td>
                <td className="max-w-xl truncate font-mono text-muted" title={JSON.stringify(e.payload)}>{JSON.stringify(e.payload)}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
