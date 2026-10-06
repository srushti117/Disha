"use client";
import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { LEVEL_COLOR, ago, fixed, num, pct } from "@/lib/format";
import { Bar, ConfBadge, ErrorBox, EstimateBadge, LevelBadge, Spinner } from "./ui";
import type { RouteLine } from "./MapView";

const COMP_LABEL: Record<string, string> = { severity: "Hazard severity", exposure: "People exposed", infrastructure: "Critical facilities", accessibility: "Road access lost" };
const COMP_COLOR: Record<string, string> = { severity: "#1d6fd8", exposure: "#d62f35", infrastructure: "#c99700", accessibility: "#1f9d6b" };

export default function CellPanel({ eventId, h3, version, onClose, onRoutes, onTime, canPlan, canAssign, canField }: {
  eventId: number; h3: string; version: number; onClose: () => void; onRoutes?: (r: RouteLine[], origin: any) => void; onTime?: (t: number) => void;
  canPlan?: boolean; canAssign?: boolean; canField?: boolean;
}) {
  const { data: c, loading, error } = useApi<any>(`/api/events/${eventId}/cells/${h3}`, { deps: [version] });
  const [routeRes, setRouteRes] = useState<any>(null);
  const [alloc, setAlloc] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function findRoute() {
    setBusy("route"); setErr(null);
    try {
      const r = await api(`/api/events/${eventId}/routes`, { body: { h3_index: h3 } });
      setRouteRes(r);
      onRoutes?.(r.routes.filter((x: any) => x.node_path?.length).map((x: any) => ({ kind: x.kind, coords: x.coords, recommended: x.recommended, blocked: x.blocked_segments > 0, label: x.label })), r.origin);
    } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  }
  async function optimise() {
    setBusy("alloc"); setErr(null);
    try {
      const r = await api(`/api/events/${eventId}/resources/optimise`, { body: { commit: true } });
      setAlloc(r.assignments.filter((a: any) => a.h3_index === h3));
    } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  }

  if (loading && !c) return <div className="panel w-[22rem]"><Spinner /></div>;
  if (!c) return <div className="panel w-[22rem] p-4"><ErrorBox error={error} /></div>;
  const comps = c.priority.components as Record<string, number>;
  const rec = routeRes?.routes.find((r: any) => r.recommended);
  return (
    <div className="panel flex max-h-full w-[22rem] flex-col overflow-hidden shadow-lg">
      <div className="flex items-start justify-between border-b border-line px-4 py-3.5" style={{ borderTop: `3px solid ${LEVEL_COLOR[c.priority.level]}` }}>
        <div>
          <div className="text-xl font-semibold text-strong">Cell {String(c.cell_no).padStart(2, "0")}</div>
          <div className="mt-1.5 flex items-center gap-2"><LevelBadge level={c.priority.level} /><span className="text-sm tabular-nums text-muted">score {fixed(c.priority.score, 2)}</span></div>
        </div>
        <div className="text-right">
          <button className="text-lg leading-none text-muted hover:text-strong" onClick={onClose} aria-label="Close">×</button>
          <div className="mt-2"><ConfBadge value={c.confidence.overall} label={c.confidence.label.replace(" CONFIDENCE", "").toLowerCase() + " confidence"} /></div>
        </div>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto px-4 py-4 text-sm">
        <section>
          <h4 className="mb-2.5 font-semibold text-strong">Why is this {c.priority.level}?</h4>
          <div className="space-y-2.5">
            {Object.entries(comps).map(([k, v]) => <Bar key={k} label={COMP_LABEL[k]} value={v} color={COMP_COLOR[k]} />)}
          </div>
          <ol className="mt-3 list-decimal space-y-1 pl-5 text-text">{c.why.top_factors.slice(0, 3).map((f: string) => <li key={f}>{f}</li>)}</ol>
          {c.field_note && <div className="mt-3 rounded-md border border-ok/40 bg-ok/10 p-2.5 text-sm text-ok">Field: {c.field_note}</div>}
        </section>

        <section className="grid grid-cols-3 gap-3 text-center">
          <Fact label="People exposed" value={num(c.population.exposed)} />
          <Fact label="Road" value={String(c.roads.status).replace("_", " ")} />
          <Fact label="Severity" value={pct(c.hazard.severity)} />
        </section>

        <section className="rounded-md bg-accent/10 p-3">
          <div className="text-xs font-medium text-accent">Recommended action</div>
          <div className="mt-0.5 text-strong">{c.recommended_action}</div>
        </section>

        <ErrorBox error={err} />
        {routeRes && (
          <section>
            <h4 className="mb-1.5 font-semibold text-strong">Route</h4>
            {rec ? (
              <div className="rounded-md border border-ok/50 bg-ok/10 p-3">
                <div className="font-medium text-strong">{rec.label}</div>
                <div className="text-sm tabular-nums text-text">{rec.distance_km} km · about {Math.round(rec.eta_min)} min · risk {pct(rec.risk)}</div>
              </div>
            ) : <div className="rounded-md border border-p1/40 bg-p1/10 p-3 text-p1">No fully open road route. Boat or air access is needed.</div>}
            {routeRes.last_mile_note && <div className="mt-2 text-xs text-warn">{routeRes.last_mile_note}</div>}
            <details className="mt-2">
              <summary className="cursor-pointer text-sm text-muted hover:text-strong">Compare all routes</summary>
              <div className="mt-2 space-y-1.5">
                {routeRes.routes.map((r: any) => (
                  <div key={r.kind} className="rounded border border-line p-2">
                    <div className="flex justify-between"><b className="text-strong">{r.label}</b>{r.recommended && <span className="text-xs font-semibold text-ok">Recommended</span>}</div>
                    {r.node_path?.length ? <div className="text-xs tabular-nums text-muted">{r.distance_km} km · {Math.round(r.eta_min)} min · {r.blocked_segments ? <span className="font-semibold text-p1">blocked ({r.blocked_segments})</span> : `risk ${pct(r.risk)}`}</div> : <div className="text-xs text-muted">{r.notes}</div>}
                  </div>
                ))}
              </div>
            </details>
          </section>
        )}
        {alloc && (
          <section>
            <h4 className="mb-1.5 font-semibold text-strong">Assigned resources</h4>
            {alloc.length === 0 ? <div className="text-muted">None assigned to this cell.</div> : <ul className="space-y-0.5">{alloc.map((a: any) => <li key={a.resource_id} title={a.reason}>{a.resource} <span className="text-muted">· about {Math.round(a.eta_min)} min</span></li>)}</ul>}
          </section>
        )}

        <details className="group border-t border-line pt-3">
          <summary className="flex cursor-pointer list-none items-center justify-between font-semibold text-strong [&::-webkit-details-marker]:hidden">More details<span className="text-muted transition group-open:rotate-180">▾</span></summary>
          <div className="mt-3 space-y-4">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
              <Fact label="Population" value={num(c.population.total)} left />
              <Fact label="At high risk" value={num(c.population.high_risk)} left />
              <Fact label="Cut off" value={num(c.population.isolated)} left />
              <Fact label="Vulnerability" value={pct(c.vulnerability.score)} left />
              <Fact label="Affected area" value={`${fixed(c.hazard.affected_area_km2, 2)} km²`} left />
              <Fact label="Nearest safe shelter" value={c.roads.nearest_shelter_km ? `${c.roads.nearest_shelter_km} km` : "–"} left />
            </dl>
            <p className="text-xs text-muted">{c.population.note || "Population figures are estimates."}</p>
            {c.infrastructure.items.length > 0 && (
              <div>
                <div className="mb-1 font-medium text-strong">Critical facilities</div>
                {c.infrastructure.items.map((i: any) => <div key={i.name} className="flex justify-between gap-3"><span className="truncate">{i.name}</span><span className={i.risk >= 0.25 ? "text-p2" : "text-muted"}>{i.status.replace("_", " ")}</span></div>)}
              </div>
            )}
            {c.cascade.reason && <div className="rounded-md border border-p2/40 bg-p2/10 p-2.5 text-sm"><b className="text-p2">Knock-on risk.</b> {c.cascade.reason}</div>}
            <div>
              <div className="mb-1 flex items-center gap-2 font-medium text-strong">Predicted level <EstimateBadge /></div>
              <table className="w-full text-sm"><tbody>
                {c.predictions.map((p: any) => (
                  <tr key={p.horizon_h} className="border-b border-line/60"><td className="py-1 tabular-nums">+{p.horizon_h} h</td><td><LevelBadge level={p.level} small /></td><td className="tabular-nums text-muted">{pct(p.probability)}</td></tr>
                ))}
              </tbody></table>
            </div>
            <div>
              <div className="mb-1 font-medium text-strong">Data used ({pct(c.confidence.overall)} overall confidence)</div>
              {c.confidence.sources.map((s: any) => (
                <div key={s.key} className="flex justify-between"><span className={s.available ? "text-text" : "text-muted"}>{s.label}</span><span className={`text-xs ${s.stale ? "text-warn" : "text-muted"}`}>{s.available ? ago(s.timestamp) : "not available"}</span></div>
              ))}
            </div>
          </div>
        </details>
      </div>

      <div className="space-y-2 border-t border-line px-4 py-3">
        <div className="grid grid-cols-2 gap-2">
          <button className="btn btn-primary" disabled={!canPlan || busy === "route"} onClick={findRoute}>{busy === "route" ? "Routing…" : "Find safest route"}</button>
          <button className="btn" disabled={!canAssign || busy === "alloc"} onClick={optimise}>{busy === "alloc" ? "Working…" : "Plan resources"}</button>
        </div>
        <div className="flex justify-between text-sm">
          <button className="text-accent hover:underline" onClick={() => onTime?.(6)}>Show +6 h estimate</button>
          {canField && <Link className="text-accent hover:underline" href={`/events/${eventId}/field?cell=${h3}`}>Field report</Link>}
        </div>
      </div>
    </div>
  );
}

function Fact({ label, value, left }: { label: string; value: string; left?: boolean }) {
  return (
    <div className={left ? "" : "rounded-md bg-panel2 px-2 py-2.5"}>
      <div className="text-xs text-muted">{label}</div>
      <div className={`${left ? "text-sm" : "text-[15px]"} font-medium capitalize tabular-nums text-strong`}>{value}</div>
    </div>
  );
}
