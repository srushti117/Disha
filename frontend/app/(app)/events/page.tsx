"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { HAZARD_LABEL, ago } from "@/lib/format";
import { DemoBadge, RealBadge, Empty, ErrorBox, PageHeader, Panel, Spinner } from "@/components/ui";

export default function Events() {
  const { can } = useAuth();
  const router = useRouter();
  const [archived, setArchived] = useState(false);
  const { data, loading, error, reload } = useApi<any[]>(`/api/events?include_archived=${archived}`);
  const { data: sc } = useApi<any>("/api/scenarios");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function quick(key: string, hazard: string) {
    setBusy(key); setErr(null);
    try {
      const e = await api("/api/events", { body: { hazard, aoi_method: "demo", scenario_key: key } });
      router.push(`/events/${e.id}`);
    } catch (ex: any) { setErr(ex.message); } finally { setBusy(null); }
  }
  async function archive(id: number) {
    try { await api(`/api/events/${id}/archive`, { method: "POST" }); reload(); } catch (ex: any) { setErr(ex.message); }
  }

  return (
    <div className="p-4">
      <PageHeader title="Events" sub="Monitor, compare and archive disaster events"
        right={<>
          <label className="flex items-center gap-1.5 text-xs text-muted"><input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} /> Show archived</label>
          {can("event.write") && <Link href="/events/new" className="btn btn-primary">+ New event</Link>}
        </>} />
      <ErrorBox error={err || error} />
      {can("event.write") && sc && (
        <Panel title="Start from a scenario" className="mb-4">
          <div className="grid gap-2 md:grid-cols-3 xl:grid-cols-5">
            {sc.scenarios.map((s: any) => (
              <button key={s.key} onClick={() => quick(s.key, s.hazard)} disabled={!!busy} className="rounded border border-line bg-panel2 p-2.5 text-left hover:border-accent disabled:opacity-50">
                <div className="mb-1 flex items-center justify-between gap-2"><span className="text-xs font-bold text-strong">{s.title}</span><span className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold ${s.mode === "live" ? "bg-ok/15 text-ok" : "bg-warn/15 text-warn"}`}>{s.mode === "live" ? "Real data" : "Simulated"}</span></div>
                <div className="text-xs leading-snug text-muted">{s.description}</div>
                <div className="mt-1.5 text-xs font-semibold text-accent">{busy === s.key ? "Creating…" : "Open →"}</div>
              </button>
            ))}
          </div>
        </Panel>
      )}
      {loading && !data ? <Spinner /> : !data?.length ? <Empty>No events yet. Start one from a demonstration scenario above.</Empty> : (
        <div className="panel overflow-x-auto">
          <table className="w-full">
            <thead><tr className="border-b border-line"><th className="th">Event</th><th className="th">Hazard</th><th className="th">Status</th><th className="th">Severity</th><th className="th">Area</th><th className="th">Assessment</th><th className="th">Last analysis</th><th className="th" /></tr></thead>
            <tbody>
              {data.map((e) => (
                <tr key={e.id} className="border-b border-line/60 hover:bg-panel2">
                  <td className="td"><Link href={`/events/${e.id}`} className="font-semibold text-strong hover:text-accent">{e.name}</Link> <span className="text-[11px] text-muted">{e.code}</span> {e.is_demo ? <DemoBadge /> : <RealBadge />}</td>
                  <td className="td">{HAZARD_LABEL[e.hazard] || e.hazard}</td>
                  <td className="td capitalize">{e.status}</td>
                  <td className="td capitalize">{e.severity}</td>
                  <td className="td tabular-nums">{e.aoi ? `${e.aoi.area_km2} km²` : "-"}</td>
                  <td className="td tabular-nums">{e.assessment_version ? `v${e.assessment_version}` : "-"}</td>
                  <td className="td text-muted">{ago(e.last_analysis)}</td>
                  <td className="td text-right">
                    <Link href={`/events/${e.id}/map`} className="btn btn-sm mr-1">Map</Link>
                    {can("event.write") && e.status !== "archived" && <button className="btn btn-sm" onClick={() => archive(e.id)}>Archive</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
