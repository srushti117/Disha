"use client";
import { useEffect, useState } from "react";
import { api, API } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { ErrorBox, PageHeader, Panel, Spinner } from "@/components/ui";

const CHANNELS = ["dashboard", "email", "sms", "whatsapp"];
const TRIGGER_LABEL: Record<string, string> = { p1_detected: "P1 detected", escalation: "P2 → P1 escalation", population_risk_increase: "Population risk increase", road_isolation: "Road isolation", hospital_risk: "Hospital risk", shelter_overload: "Shelter overload", prediction_threshold: "Prediction threshold crossed", field_severe: "Field report confirms severe damage" };

export default function Settings() {
  const { user, can } = useAuth();
  const { data: events } = useApi<any[]>("/api/events");
  const { data: perms } = useApi<Record<string, string[]>>("/api/permissions");
  const { data: health } = useApi<any>("/api/health");
  const [id, setId] = useState<number | null>(null);
  useEffect(() => { if (events?.length && !id) setId(events[0].id); }, [events, id]);
  const { data: al, reload } = useApi<any>(id ? `/api/events/${id}/alerts` : null);
  const [cfg, setCfg] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => { if (al) setCfg(al.config); }, [al]);

  async function save() {
    setErr(null); setSaved(false);
    try { await api(`/api/events/${id}/alerts/config`, { method: "PUT", body: cfg }); setSaved(true); reload(); } catch (e: any) { setErr(e.message); }
  }
  return (
    <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
      <PageHeader title="Settings" sub="Alerts, roles and platform information" />
      <Panel title="Alert engine" right={events && <select className="input w-64" value={id ?? ""} onChange={(e) => setId(+e.target.value)}>{events.map((e) => <option key={e.id} value={e.id}>{e.code} · {e.name}</option>)}</select>}>
        {!cfg ? <Spinner /> : (
          <>
            <table className="w-full"><thead><tr className="border-b border-line"><th className="th">Trigger</th><th className="th">On</th>{CHANNELS.map((c) => <th key={c} className="th capitalize">{c}</th>)}</tr></thead>
              <tbody>{Object.entries(cfg).map(([k, v]: any) => (
                <tr key={k} className="border-b border-line/60"><td className="td">{TRIGGER_LABEL[k] || k}</td>
                  <td className="td"><input type="checkbox" checked={v.enabled} disabled={!can("priority.configure")} onChange={(e) => setCfg({ ...cfg, [k]: { ...v, enabled: e.target.checked } })} /></td>
                  {CHANNELS.map((c) => <td key={c} className="td"><input type="checkbox" checked={v.channels.includes(c)} disabled={!can("priority.configure")} onChange={(e) => setCfg({ ...cfg, [k]: { ...v, channels: e.target.checked ? [...v.channels, c] : v.channels.filter((x: string) => x !== c) } })} /></td>)}</tr>
              ))}</tbody></table>
            <ErrorBox error={err} />
            <div className="mt-3 flex items-center gap-3"><button className="btn btn-primary" disabled={!can("priority.configure")} onClick={save}>Save alert configuration</button>{saved && <span className="text-xs text-ok">Saved.</span>}</div>
            <p className="mt-2 text-xs text-warn">{al?.note || "Notification provider is not mock - make sure credentials are configured."} Email/SMS/WhatsApp use provider abstractions; in demo mode they are recorded as MOCK_SENT.</p>
          </>
        )}
      </Panel>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Your access"><div className="text-xs">Signed in as <b className="text-strong">{user?.email}</b> · role <b className=" text-accent">{user?.role}</b></div>
          <div className="mt-2 flex flex-wrap gap-1">{user?.permissions?.map((p) => <span key={p} className="rounded border border-line px-1.5 py-0.5 tabular-nums text-[11px] text-muted">{p}</span>)}</div></Panel>
        <Panel title="Platform"><dl className="space-y-1 text-xs"><div className="flex justify-between"><dt className="text-muted">API</dt><dd className="tabular-nums">{API}</dd></div><div className="flex justify-between"><dt className="text-muted">Status</dt><dd>{health?.status}</dd></div><div className="flex justify-between"><dt className="text-muted">Database</dt><dd className="tabular-nums">{health?.database}</dd></div><div className="flex justify-between"><dt className="text-muted">Demo mode</dt><dd>{String(health?.demo_mode)}</dd></div><div className="flex justify-between"><dt className="text-muted">Notifications</dt><dd className="tabular-nums">{health?.notify_provider}</dd></div></dl></Panel>
      </div>
      {perms && (
        <Panel title="Role permissions" pad={false}>
          <table className="w-full"><thead><tr className="border-b border-line"><th className="th">Permission</th>{["admin", "commander", "analyst", "responder", "observer"].map((r) => <th key={r} className="th capitalize">{r}</th>)}</tr></thead>
            <tbody>{Object.entries(perms).map(([p, roles]) => <tr key={p} className="border-b border-line/60"><td className="td tabular-nums text-xs">{p}</td>{["admin", "commander", "analyst", "responder", "observer"].map((r) => <td key={r} className="td">{roles.includes(r) ? <span className="text-ok">●</span> : <span className="text-line">○</span>}</td>)}</tr>)}</tbody></table>
        </Panel>
      )}
    </div>
  );
}
