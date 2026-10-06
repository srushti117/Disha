"use client";
import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { LEVEL_COLOR, ago, fixed, num, pct } from "@/lib/format";
import { Bar, ConfBadge, ErrorBox, EstimateBadge, LevelBadge, Spinner } from "./ui";
import type { RouteLine } from "./MapView";

const COMP_LABEL: Record<string, string> = { severity: "Severity", exposure: "Population", infrastructure: "Infrastructure", accessibility: "Accessibility" };
const COMP_COLOR: Record<string, string> = { severity: "#3b9eff", exposure: "#e5484d", infrastructure: "#f2c744", accessibility: "#35c28a" };

export default function CellPanel({ eventId, h3, version, onClose, onRoutes, onTime, canPlan, canAssign, canField }: {
  eventId: number; h3: string; version: number; onClose: () => void; onRoutes?: (r: RouteLine[], origin: any) => void; onTime?: (t: number) => void;
  canPlan?: boolean; canAssign?: boolean; canField?: boolean;
}) {
  const { data: c, loading, error, reload } = useApi<any>(`/api/events/${eventId}/cells/${h3}`, { deps: [version] });
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

  if (loading && !c) return <div className="panel w-80"><Spinner /></div>;
  if (!c) return <div className="panel w-80 p-3"><ErrorBox error={error} /></div>;
  const comps = c.priority.components as Record<string, number>;
  const color = LEVEL_COLOR[c.priority.level];
  return (
    <div className="panel flex max-h-full w-[22rem] flex-col overflow-hidden">
      <div className="flex items-start justify-between border-b border-line p-3" style={{ borderTop: `3px solid ${color}` }}>
        <div>
          <div className="text-[11px] font-semibold   text-muted">H3 CELL</div>
          <div className="tabular-nums text-2xl font-bold text-strong">CELL {String(c.cell_no).padStart(2, "0")}</div>
          <div className="mt-1 flex items-center gap-2"><LevelBadge level={c.priority.level} /><span className="tabular-nums text-xs text-muted">PI {fixed(c.priority.score, 2)}</span></div>
        </div>
        <div className="text-right">
          <button className="text-muted hover:text-strong" onClick={onClose} aria-label="Close">✕</button>
          <div className="mt-2"><ConfBadge value={c.confidence.overall} label={c.confidence.label} /></div>
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-3 text-xs">
        <section>
          <h4 className="mb-1.5 text-xs font-bold   text-muted">Why is this {c.priority.level}?</h4>
          <div className="space-y-1.5">
            {Object.entries(comps).map(([k, v]) => (
              <Bar key={k} label={`${COMP_LABEL[k]} (w ${pct(c.priority.weights[k])})`} value={v} color={COMP_COLOR[k]} />
            ))}
          </div>
          <div className="mt-2 text-xs font-semibold text-muted">Top factors</div>
          <ol className="ml-4 list-decimal space-y-0.5 text-text">
            {c.why.top_factors.map((f: string) => <li key={f}>{f}</li>)}
          </ol>
          {c.field_note && <div className="mt-2 rounded border border-ok/40 bg-ok/10 p-2 text-xs text-ok">FIELD: {c.field_note}</div>}
        </section>

        <section className="grid grid-cols-2 gap-x-3 gap-y-1.5">
          <KV k="Hazard severity" v={pct(c.hazard.severity)} /><KV k="Affected area" v={`${fixed(c.hazard.affected_area_km2, 2)} km²`} />
          <KV k="Population" v={num(c.population.total)} /><KV k="Exposed" v={num(c.population.exposed)} />
          <KV k="High risk" v={num(c.population.high_risk)} /><KV k="Potentially isolated" v={num(c.population.isolated)} />
          <KV k="Vulnerable (est.)" v={num(c.population.vulnerable)} /><KV k="Vulnerability score" v={pct(c.vulnerability.score)} />
          <KV k="Road" v={String(c.roads.status).replace("_", " ")} /><KV k="Access loss" v={pct(c.roads.access_loss)} />
          <KV k="Nearest safe shelter" v={c.roads.nearest_shelter_km ? `${c.roads.nearest_shelter_km} km` : "-"} /><KV k="Cascade risk" v={pct(c.cascade.risk)} />
        </section>
        <div className="text-[11px] text-muted">{c.population.note || "Population figures are estimates."}</div>

        {c.infrastructure.items.length > 0 && (
          <section>
            <h4 className="mb-1 text-xs font-bold   text-muted">Critical infrastructure</h4>
            {c.infrastructure.items.map((i: any) => (
              <div key={i.name} className="flex justify-between"><span>{i.name} <span className="text-muted">({i.kind})</span></span><span className={i.risk >= 0.25 ? "text-p2" : "text-muted"}>{i.status.replace("_", " ")}</span></div>
            ))}
          </section>
        )}
        {c.cascade.reason && <section className="rounded border border-p2/40 bg-p2/10 p-2 text-xs"><b className="text-p2">CASCADE RISK</b><br />{c.cascade.reason}</section>}

        <section>
          <h4 className="mb-1 flex items-center gap-2 text-xs font-bold   text-muted">Predicted risk <EstimateBadge /></h4>
          <table className="w-full"><tbody>
            {c.predictions.map((p: any) => (
              <tr key={p.horizon_h} className="border-b border-line/50">
                <td className="py-1 tabular-nums">+{p.horizon_h}h</td><td><LevelBadge level={p.level} small /></td>
                <td className="tabular-nums">{pct(p.probability)}</td><td className="text-right text-[11px] text-muted">{p.confidence_label.replace(" CONFIDENCE", "")}</td>
              </tr>
            ))}
          </tbody></table>
        </section>

        <section>
          <h4 className="mb-1 text-xs font-bold   text-muted">Data sources</h4>
          <div className="grid grid-cols-2 gap-x-3">
            {c.confidence.sources.map((s: any) => (
              <div key={s.key} className="flex items-center justify-between">
                <span className={s.available ? "text-text" : "text-muted"}>{s.available ? "✓" : "✗"} {s.label}</span>
                <span className={`text-[11px] ${s.stale ? "text-warn" : "text-muted"}`}>{s.available ? ago(s.timestamp) : "n/a"}{s.simulated && s.available ? " · sim" : ""}</span>
              </div>
            ))}
          </div>
          <div className="mt-1 text-xs">Overall confidence <b className="tabular-nums text-strong">{pct(c.confidence.overall)}</b> · detection {pct(c.confidence.detection)}</div>
        </section>

        <section className="rounded border border-accent/40 bg-accent/10 p-2">
          <div className="text-[11px] font-bold   text-accent">Recommended action</div>
          <div className="text-[12px] text-strong">{c.recommended_action}</div>
        </section>

        <ErrorBox error={err} />
        {routeRes && (
          <section>
            <h4 className="mb-1 text-xs font-bold   text-muted">Route comparison</h4>
            {routeRes.routes.map((r: any) => (
              <div key={r.kind} className={`mb-1 rounded border p-1.5 ${r.recommended ? "border-ok bg-ok/10" : "border-line"}`}>
                <div className="flex justify-between"><b>{r.label}</b>{r.recommended && <span className="text-[11px] font-bold text-ok">RECOMMENDED</span>}</div>
                {r.node_path?.length ? <div className="tabular-nums text-xs">{r.distance_km} km · ETA {Math.round(r.eta_min)} min · {r.blocked_segments ? <span className="text-p1">BLOCKED ({r.blocked_segments})</span> : `risk ${pct(r.risk)}`}</div> : <div className="text-muted">{r.notes}</div>}
              </div>
            ))}
            {routeRes.last_mile_note && <div className="text-xs text-warn">{routeRes.last_mile_note}</div>}
          </section>
        )}
        {alloc && (
          <section>
            <h4 className="mb-1 text-xs font-bold   text-muted">Assigned resources</h4>
            {alloc.length === 0 ? <div className="text-muted">No units assigned to this cell (not P1/P2 or none available).</div> : alloc.map((a: any) => <div key={a.resource_id} title={a.reason}>→ {a.resource} <span className="text-muted">(ETA {Math.round(a.eta_min)} min)</span></div>)}
          </section>
        )}
      </div>

      <div className="grid grid-cols-2 gap-1.5 border-t border-line p-2">
        <button className="btn btn-sm" onClick={() => onTime?.(6)}>Predict next 6 h</button>
        <button className="btn btn-sm btn-primary" disabled={!canPlan || busy === "route"} onClick={findRoute}>{busy === "route" ? "Routing…" : "Find safest route"}</button>
        <button className="btn btn-sm" disabled={!canAssign || busy === "alloc"} onClick={optimise}>{busy === "alloc" ? "Optimising…" : "Optimise resources"}</button>
        {canField ? <Link className="btn btn-sm" href={`/events/${eventId}/field?cell=${h3}`}>Field report</Link> : <button className="btn btn-sm" onClick={reload}>Refresh</button>}
      </div>
    </div>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return <div><div className="text-[11px]   text-muted">{k}</div><div className="tabular-nums text-[13px] text-strong">{v}</div></div>;
}
