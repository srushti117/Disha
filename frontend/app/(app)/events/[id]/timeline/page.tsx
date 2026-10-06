"use client";
import { useParams } from "next/navigation";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { hhmm, dt } from "@/lib/format";
import { useEvent } from "@/components/EventContext";
import { PageHeader, Panel, Spinner } from "@/components/ui";

const KIND_COLOR: Record<string, string> = { alert: "#e5484d", satellite: "#3b9eff", detection: "#3b9eff", priority: "#f08a24", escalation: "#e5484d", plan: "#9b8cff", resource: "#35c28a", dispatch: "#35c28a", field: "#35c28a", report: "#7b8ca5", created: "#7b8ca5", status: "#7b8ca5" };

export default function Timeline() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const { event } = useEvent();
  const version = event?.assessment_version ?? 0;
  const { data, loading } = useApi<any[]>(`/api/events/${id}/timeline`, { deps: [version], poll: 6000 });
  const { data: audit } = useApi<any[]>(can("event.write") ? `/api/admin/audit?event_id=${id}&limit=100` : null, { deps: [version] });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div>
        <PageHeader title="Incident timeline" sub="Operational record of detection, decisions and field feedback" />
        {loading && !data ? <Spinner /> : (
          <ol className="panel space-y-0 p-3">
            {data?.map((t) => (
              <li key={t.id} className="flex gap-3 border-l border-line pb-3 pl-3" style={{ borderLeftColor: KIND_COLOR[t.kind] || "#1e2b40" }}>
                <div className="w-20 shrink-0 whitespace-nowrap tabular-nums text-xs text-muted">{hhmm(t.at)}</div>
                <div className="min-w-0"><div className="text-xs font-semibold text-strong">{t.title}</div>{t.detail && <div className="text-xs text-muted">{t.detail}</div>}</div>
              </li>
            ))}
          </ol>
        )}
      </div>
      <div>
        <PageHeader title="Audit log" sub="Who · what · where · when" />
        {!can("event.write") ? <div className="panel p-4 text-xs text-muted">Audit log is visible to commanders, analysts and admins.</div> : (
          <Panel pad={false}>
            <table className="w-full"><thead><tr className="border-b border-line"><th className="th">When</th><th className="th">Who</th><th className="th">What</th><th className="th">Where / why</th></tr></thead>
              <tbody>{audit?.map((a) => (
                <tr key={a.id} className="border-b border-line/60 align-top"><td className="td tabular-nums text-[11px] text-muted">{dt(a.at)}</td><td className="td text-xs">{a.who}</td><td className="td tabular-nums text-xs text-strong">{a.what}</td><td className="td text-xs text-muted">{a.where}{a.reason ? ` - ${a.reason}` : ""}</td></tr>
              ))}</tbody></table>
          </Panel>
        )}
      </div>
    </div>
  );
}
