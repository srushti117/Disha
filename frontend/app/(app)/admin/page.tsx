"use client";
import { useState } from "react";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { dt } from "@/lib/format";
import { Empty, PageHeader, Panel, Tabs } from "@/components/ui";

type Tab = "users" | "audit" | "models" | "sources";

export default function Admin() {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("users");
  const isAdmin = user?.role === "admin";
  const { data: users } = useApi<any[]>(isAdmin ? "/api/admin/users" : null);
  const { data: audit } = useApi<any[]>(isAdmin ? "/api/admin/audit?limit=300" : null, { poll: 10000 });
  const { data: models } = useApi<any[]>("/api/models");
  const { data: sources } = useApi<any[]>(isAdmin ? "/api/admin/data-sources" : null);
  if (!isAdmin) return <div className="p-4"><Empty>Administrator access required.</Empty></div>;
  return (
    <div className="p-4">
      <PageHeader title="Administration" sub="Users, audit trail, model registry and data sources" />
      <Panel pad={false}>
        <Tabs<Tab> value={tab} onChange={setTab} tabs={[{ key: "users", label: "Users" }, { key: "audit", label: "Audit log" }, { key: "models", label: "Models" }, { key: "sources", label: "Data sources" }]} />
        <div className="overflow-x-auto">
          {tab === "users" && <table className="w-full"><thead><tr className="border-b border-line"><th className="th">Name</th><th className="th">Email</th><th className="th">Role</th><th className="th">Demo account</th></tr></thead><tbody>{users?.map((u) => <tr key={u.id} className="border-b border-line/60"><td className="td">{u.name}</td><td className="td tabular-nums">{u.email}</td><td className="td capitalize">{u.role}</td><td className="td">{u.is_demo ? <span className="text-warn">DEMO</span> : ""}</td></tr>)}</tbody></table>}
          {tab === "audit" && <table className="w-full"><thead><tr className="border-b border-line"><th className="th">When</th><th className="th">Who</th><th className="th">What</th><th className="th">Where</th><th className="th">Reason</th></tr></thead><tbody>{audit?.map((a) => <tr key={a.id} className="border-b border-line/60 align-top"><td className="td tabular-nums text-[11px] text-muted">{dt(a.at)}</td><td className="td text-xs">{a.who}</td><td className="td tabular-nums text-xs text-strong">{a.what}</td><td className="td text-xs">{a.where}</td><td className="td text-xs text-muted">{a.reason}</td></tr>)}</tbody></table>}
          {tab === "models" && <table className="w-full"><thead><tr className="border-b border-line"><th className="th">Model</th><th className="th">Hazard</th><th className="th">Kind</th><th className="th">Status</th><th className="th">Training data</th><th className="th">Accuracy</th><th className="th">Notes</th></tr></thead><tbody>{models?.map((m) => <tr key={m.id} className="border-b border-line/60 align-top"><td className="td tabular-nums">{m.name} v{m.version}</td><td className="td">{m.hazard}</td><td className="td capitalize">{m.kind}</td><td className="td capitalize">{m.status.replace("_", " ")}</td><td className="td text-muted">{m.training_dataset}</td><td className="td tabular-nums">{m.accuracy ?? "unknown"}</td><td className="td text-xs text-muted">{m.notes}</td></tr>)}</tbody></table>}
          {tab === "sources" && <table className="w-full"><thead><tr className="border-b border-line"><th className="th">Event</th><th className="th">Key</th><th className="th">Name</th><th className="th">Simulated</th><th className="th">Quality</th><th className="th">Updated</th></tr></thead><tbody>{sources?.map((s, i) => <tr key={i} className="border-b border-line/60"><td className="td tabular-nums">{s.event_id}</td><td className="td">{s.key}</td><td className="td">{s.name}</td><td className="td">{s.simulated ? <span className="text-warn">SIMULATED</span> : "live"}</td><td className="td tabular-nums">{Math.round(s.quality * 100)}%</td><td className="td text-muted">{dt(s.last_updated)}</td></tr>)}</tbody></table>}
        </div>
      </Panel>
    </div>
  );
}
