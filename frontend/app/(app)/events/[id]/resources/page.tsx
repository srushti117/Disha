"use client";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { LEVEL_COLOR } from "@/lib/format";
import { useEvent } from "@/components/EventContext";
import { Empty, ErrorBox, LevelBadge, PageHeader, Panel, Spinner, Stat } from "@/components/ui";

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

  useEffect(() => { if (data && !Object.keys(counts).length) setCounts(data.available); }, [data, counts]);
  if (!version) return <Empty>Run analysis to load the resource roster.</Empty>;
  if (!data) return <Spinner />;
  const run = async (name: string, fn: () => Promise<any>) => { setBusy(name); setErr(null); try { await fn(); } catch (e: any) { setErr(e.message); } finally { setBusy(null); } };
  const canAssign = can("resource.assign");
  const m = opt?.metrics;

  return (
    <div className="space-y-4">
      <PageHeader title="Resource command" sub="Rule-based, explainable allocation of rescue resources to P1/P2 cells" />
      <ErrorBox error={err} />
      {event && !event.is_demo && <div className="rounded border border-warn/40 bg-warn/10 p-2 text-xs text-warn">The roster below is hypothetical: there is no real resource feed. Units are placed at the listed response bases so allocation and ETAs can be demonstrated; replace with real unit data before operational use.</div>}
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Available">
          <div className="space-y-1.5">{data.kinds.map((k: any) => <div key={k.kind} className="flex justify-between text-sm"><span>{k.label}s</span><span className="tabular-nums font-bold text-strong">{data.available[k.kind]}</span></div>)}</div>
        </Panel>
        <Panel title="Deployed">
          <div className="space-y-1.5">{data.kinds.map((k: any) => <div key={k.kind} className="flex justify-between text-sm"><span>{k.label}s</span><span className="tabular-nums font-bold text-strong">{data.deployed[k.kind]}</span></div>)}</div>
        </Panel>
        <Panel title="Unassigned P1">
          <Stat big label="locations" value={data.unassigned_p1.length} sub={`of ${data.p1_total} P1`} color={data.unassigned_p1.length ? LEVEL_COLOR.P1 : "#35c28a"} />
          <div className="mt-2 flex flex-wrap gap-1">{data.unassigned_p1.slice(0, 20).map((c: any) => <span key={c.h3_index} className="rounded bg-p1/15 px-1.5 py-0.5 tabular-nums text-[11px] text-p1">{String(c.cell_no).padStart(2, "0")}</span>)}</div>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Resource simulation (what-if)" right={<span className="text-[11px] text-muted">nothing is dispatched</span>}>
          <div className="grid grid-cols-3 gap-2">
            {data.kinds.map((k: any) => (
              <div key={k.kind}><label className="label">{k.label}s</label><input type="number" min={0} max={200} className="input tabular-nums" value={counts[k.kind] ?? 0} onChange={(e) => setCounts({ ...counts, [k.kind]: Math.max(0, +e.target.value) })} /></div>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <button className="btn btn-primary" disabled={!canAssign || busy === "sim"} onClick={() => run("sim", async () => setSim(await api(`/api/events/${id}/resources/simulate`, { body: { counts } })))}>{busy === "sim" ? "Simulating…" : "Simulate"}</button>
            <button className="btn" disabled={!canAssign || busy === "roster"} onClick={() => run("roster", async () => { await api(`/api/events/${id}/resources/roster`, { method: "PUT", body: { counts } }); reload(); })} title="Make this the real available roster">Apply as roster</button>
          </div>
          {sim && (
            <div className="mt-3 grid grid-cols-3 gap-3 rounded border border-line bg-panel2 p-3">
              <Stat label="P1 coverage" value={sim.metrics.p1_coverage_pct != null ? `${sim.metrics.p1_coverage_pct}%` : "-"} />
              <Stat label="Unserved P1" value={sim.metrics.unserved_p1_count} color={sim.metrics.unserved_p1_count ? LEVEL_COLOR.P1 : "#35c28a"} />
              <Stat label="Est. response delay" value={sim.metrics.est_response_delay_min != null ? `${sim.metrics.est_response_delay_min} min` : "-"} />
              <div className="col-span-3 text-[11px] text-muted">{sim.note} {sim.metrics.note}</div>
            </div>
          )}
        </Panel>

        <Panel title="Optimise & dispatch" right={m && <span className="text-[11px] text-muted">coverage {m.p1_coverage_pct}%</span>}>
          <div className="flex flex-wrap gap-2">
            <button className="btn btn-primary" disabled={!canAssign || busy === "opt"} onClick={() => run("opt", async () => { setOpt(await api(`/api/events/${id}/resources/optimise`, { body: { commit: true } })); reload(); refresh(); })}>{busy === "opt" ? "Optimising…" : "Optimise resources"}</button>
            <button className="btn" disabled={!canAssign || busy === "disp" || !data.assignments.some((a: any) => a.status === "recommended")} onClick={() => run("disp", async () => { await api(`/api/events/${id}/resources/dispatch`, { body: { reason: "Commander dispatch of recommended allocation" } }); reload(); refresh(); })}>{busy === "disp" ? "Dispatching…" : "Dispatch recommended"}</button>
            <button className="btn btn-danger" disabled={!canAssign} onClick={() => run("rel", async () => { await api(`/api/events/${id}/resources/release`, { method: "POST" }); reload(); refresh(); })}>Release all</button>
          </div>
          {m && (
            <div className="mt-3 grid grid-cols-3 gap-3 rounded border border-line bg-panel2 p-3">
              <Stat label="P1 coverage" value={`${m.p1_coverage_pct ?? "-"}%`} sub={`${m.p1_served}/${m.p1_total} served`} />
              <Stat label="Units assigned" value={m.units_assigned} />
              <Stat label="Est. delay" value={m.est_response_delay_min != null ? `${m.est_response_delay_min} min` : "-"} sub="slowest P1 first response" />
            </div>
          )}
          {opt?.unmet?.length > 0 && <div className="mt-2 rounded border border-p1/40 bg-p1/10 p-2 text-xs text-p1">Unmet requirements: {opt.unmet.slice(0, 6).map((u: any) => `Cell ${String(u.cell_no).padStart(2, "0")} needs ${u.kind.replace("_", " ")}`).join("; ")}</div>}
          {!canAssign && <p className="mt-2 text-xs text-muted">Your role can view but not assign resources.</p>}
        </Panel>
      </div>

      <Panel title={`Assignments (${data.assignments.length})`} pad={false}>
        {!data.assignments.length ? <div className="p-4 text-xs text-muted">No assignments yet. Click “Optimise resources”.</div> : (
          <table className="w-full"><thead><tr className="border-b border-line"><th className="th">Resource</th><th className="th">→ Cell</th><th className="th">ETA</th><th className="th">Status</th><th className="th">Why</th></tr></thead>
            <tbody>{data.assignments.map((a: any) => (
              <tr key={a.id} className="border-b border-line/60"><td className="td font-semibold text-strong">{a.resource}</td><td className="td tabular-nums">{String(a.cell_no).padStart(2, "0")}</td><td className="td tabular-nums">{Math.round(a.eta_min)} min</td>
                <td className="td"><span className={`text-[11px] font-bold  ${a.status === "dispatched" ? "text-ok" : "text-warn"}`}>{a.status}</span></td><td className="td text-xs text-muted">{a.reason}</td></tr>
            ))}</tbody></table>
        )}
      </Panel>
      <Panel title="Roster" pad={false}>
        <div className="flex max-h-60 flex-wrap gap-1 overflow-y-auto p-3">
          {data.roster.map((r: any) => <span key={r.id} className={`rounded border px-1.5 py-0.5 text-[11px] ${r.status === "deployed" ? "border-ok text-ok" : r.status === "available" ? "border-line text-text" : "border-line text-muted line-through"}`}>{r.name}</span>)}
        </div>
      </Panel>
    </div>
  );
}
