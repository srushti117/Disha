"use client";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { LEVEL_COLOR } from "@/lib/format";
import { useEvent } from "@/components/EventContext";
import { Disclosure, Empty, ErrorBox, PageHeader, Panel, Spinner, Stat } from "@/components/ui";

export default function Resources() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const { event, refresh } = useEvent();
  const version = event?.assessment_version ?? 0;
  const { data, reload } = useApi<any>(`/api/events/${id}/resources`, { deps: [version] });
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [sim, setSim] = useState<any>(null);
  const [opt, setOpt] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [allRows, setAllRows] = useState(false);

  useEffect(() => { if (data && !Object.keys(counts).length) setCounts(data.available); }, [data, counts]);
  if (!version) return <Empty>Run the analysis first to plan resources.</Empty>;
  if (!data) return <Spinner />;
  const run = async (name: string, fn: () => Promise<any>) => { setBusy(name); setErr(null); try { await fn(); } catch (e: any) { setErr(e.message); } finally { setBusy(null); } };
  const canAssign = can("resource.assign");
  const m = opt?.metrics;
  const rows: any[] = allRows ? data.assignments : data.assignments.slice(0, 8);
  const free = data.kinds.map((k: any) => `${data.available[k.kind]} ${k.label.toLowerCase()}${data.available[k.kind] === 1 ? "" : "s"}`).join(", ");

  return (
    <div className="space-y-6">
      <PageHeader title="Resources" sub="Decide which teams, boats and ambulances go where" />
      <ErrorBox error={err} />
      {event && !event.is_demo && <div className="rounded-md border border-warn/40 bg-warn/10 p-3 text-sm text-warn">The units here are hypothetical: there is no real resource feed. Replace them with real unit data before operational use.</div>}

      <Panel title="Plan and dispatch">
        <div className="flex flex-wrap items-center gap-3">
          <button className="btn btn-primary" disabled={!canAssign || busy === "opt"} onClick={() => run("opt", async () => { setOpt(await api(`/api/events/${id}/resources/optimise`, { body: { commit: true } })); reload(); refresh(); })}>{busy === "opt" ? "Planning…" : "Plan resources"}</button>
          <button className="btn" disabled={!canAssign || busy === "disp" || !data.assignments.some((a: any) => a.status === "recommended")} onClick={() => run("disp", async () => { await api(`/api/events/${id}/resources/dispatch`, { body: { reason: "Commander dispatch of recommended allocation" } }); reload(); refresh(); })}>{busy === "disp" ? "Dispatching…" : "Dispatch"}</button>
          <button className="btn" disabled={!canAssign} onClick={() => run("rel", async () => { await api(`/api/events/${id}/resources/release`, { method: "POST" }); reload(); refresh(); })}>Release all</button>
          <span className="text-sm text-muted">Free units: {free}</span>
        </div>
        <div className="mt-5 grid grid-cols-3 gap-6">
          <Stat label="Critical areas without a team" value={data.unassigned_p1.length} sub={`of ${data.p1_total}`} color={data.unassigned_p1.length ? LEVEL_COLOR.P1 : "#1f9d6b"} />
          <Stat label="Critical areas covered" value={m ? `${m.p1_coverage_pct ?? "–"}%` : "–"} sub={m ? `${m.p1_served} of ${m.p1_total}` : "plan resources to see this"} />
          <Stat label="Slowest first arrival" value={m?.est_response_delay_min != null ? `${m.est_response_delay_min} min` : "–"} sub="estimate" />
        </div>
        {opt?.unmet?.length > 0 && <div className="mt-4 rounded-md border border-p1/40 bg-p1/10 p-3 text-sm text-p1">Not enough units for: {opt.unmet.slice(0, 5).map((u: any) => `Cell ${String(u.cell_no).padStart(2, "0")} (${u.kind.replace("_", " ")})`).join(", ")}</div>}
        {!canAssign && <p className="mt-3 text-sm text-muted">Your role can view resources but not assign them.</p>}
      </Panel>

      <Panel title={`Assignments (${data.assignments.length})`} pad={false}>
        {!data.assignments.length ? <div className="p-5 text-sm text-muted">Nothing assigned yet. Press “Plan resources”.</div> : (
          <>
            <table className="w-full">
              <thead><tr className="border-b border-line"><th className="th">Unit</th><th className="th">Area</th><th className="th">Arrives in</th><th className="th">Status</th></tr></thead>
              <tbody>{rows.map((a: any) => (
                <tr key={a.id} className="border-b border-line/60 align-top">
                  <td className="td"><div className="font-medium text-strong">{a.resource}</div><div className="text-xs text-muted">{a.reason}</div></td>
                  <td className="td tabular-nums">Cell {String(a.cell_no).padStart(2, "0")}</td>
                  <td className="td tabular-nums">{Math.round(a.eta_min)} min</td>
                  <td className="td"><span className={`text-sm ${a.status === "dispatched" ? "text-ok" : "text-warn"}`}>{a.status === "dispatched" ? "Dispatched" : "Planned"}</span></td>
                </tr>
              ))}</tbody>
            </table>
            {data.assignments.length > 8 && <button className="w-full border-t border-line py-2.5 text-sm text-accent hover:underline" onClick={() => setAllRows((a) => !a)}>{allRows ? "Show fewer" : `Show all ${data.assignments.length}`}</button>}
          </>
        )}
      </Panel>

      <div className="space-y-3">
        <Disclosure title="Try a different number of units (what-if)" hint="nothing is dispatched">
          <div className="grid grid-cols-3 gap-4">
            {data.kinds.map((k: any) => (
              <div key={k.kind}><label className="label">{k.label}s</label><input type="number" min={0} max={200} className="input tabular-nums" value={counts[k.kind] ?? 0} onChange={(e) => setCounts({ ...counts, [k.kind]: Math.max(0, +e.target.value) })} /></div>
            ))}
          </div>
          <div className="mt-4 flex gap-3">
            <button className="btn btn-primary" disabled={!canAssign || busy === "sim"} onClick={() => run("sim", async () => setSim(await api(`/api/events/${id}/resources/simulate`, { body: { counts } })))}>{busy === "sim" ? "Calculating…" : "Calculate"}</button>
            <button className="btn" disabled={!canAssign || busy === "roster"} onClick={() => run("roster", async () => { await api(`/api/events/${id}/resources/roster`, { method: "PUT", body: { counts } }); reload(); })}>Use these numbers</button>
          </div>
          {sim && (
            <div className="mt-5 grid grid-cols-3 gap-6 rounded-md bg-panel2 p-4">
              <Stat label="Critical areas covered" value={sim.metrics.p1_coverage_pct != null ? `${sim.metrics.p1_coverage_pct}%` : "–"} />
              <Stat label="Critical areas missed" value={sim.metrics.unserved_p1_count} color={sim.metrics.unserved_p1_count ? LEVEL_COLOR.P1 : "#1f9d6b"} />
              <Stat label="Slowest first arrival" value={sim.metrics.est_response_delay_min != null ? `${sim.metrics.est_response_delay_min} min` : "–"} />
              <div className="col-span-3 text-xs text-muted">{sim.note} {sim.metrics.note}</div>
            </div>
          )}
        </Disclosure>
        <Disclosure title="All units" hint={`${data.roster.length}`}>
          <div className="flex flex-wrap gap-1.5">
            {data.roster.map((r: any) => <span key={r.id} className={`rounded-full border px-2.5 py-0.5 text-xs ${r.status === "deployed" ? "border-ok text-ok" : r.status === "available" ? "border-line text-text" : "border-line text-muted line-through"}`}>{r.name}</span>)}
          </div>
        </Disclosure>
      </div>
    </div>
  );
}
