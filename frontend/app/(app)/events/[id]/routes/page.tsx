"use client";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { pct } from "@/lib/format";
import { useEvent } from "@/components/EventContext";
import { DEFAULT_LAYERS, RouteLine } from "@/components/MapView";
import { Empty, ErrorBox, LevelBadge, PageHeader, Panel, Spinner } from "@/components/ui";

const MapView = dynamic(() => import("@/components/MapView"), { ssr: false, loading: () => <Spinner /> });

export default function RoutesPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const { event } = useEvent();
  const version = event?.assessment_version ?? 0;
  const { data: map } = useApi<any>(`/api/events/${id}/map?t=0`, { deps: [version] });
  const { data: p1 } = useApi<any>(`/api/events/${id}/priorities?level=P1,P2&limit=60`, { deps: [version] });
  const { data: stored } = useApi<any>(`/api/events/${id}/routes`, { deps: [version] });
  const [target, setTarget] = useState<string>("");
  const [originSel, setOriginSel] = useState("base:0");
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const bases: any[] = stored?.bases || [];

  useEffect(() => { if (p1 && !target && p1.cells.length) setTarget(p1.cells[0].h3_index); }, [p1, target]);

  async function go() {
    setBusy(true); setErr(null);
    try {
      const b = originSel.startsWith("base:") ? bases[+originSel.slice(5)] : null;
      setRes(await api(`/api/events/${id}/routes`, { body: { h3_index: target, origin_lat: b?.lat, origin_lon: b?.lon } }));
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }
  const lines: RouteLine[] = useMemo(() => (res ? res.routes.filter((r: any) => r.node_path?.length).map((r: any) => ({ kind: r.kind, coords: r.coords, recommended: r.recommended, blocked: r.blocked_segments > 0 })) : []), [res]);
  if (!version) return <Empty>Run analysis to plan rescue routes.</Empty>;

  return (
    <div className="space-y-6">
      <PageHeader title="Rescue route optimiser" sub="Shortest, fastest and safest routes over the hazard-aware road graph" />
      <div className="grid gap-6 xl:grid-cols-[22rem_1fr]">
        <div className="space-y-6">
          <Panel title="Plan route">
            <label className="label" htmlFor="tgt">Target cell</label>
            <select id="tgt" className="input" value={target} onChange={(e) => setTarget(e.target.value)}>
              {p1?.cells.map((c: any) => <option key={c.h3_index} value={c.h3_index}>Cell {String(c.cell_no).padStart(2, "0")} · {c.level} · {c.score.toFixed(2)}</option>)}
            </select>
            <label className="label mt-3" htmlFor="org">Responder origin</label>
            <select id="org" className="input" value={originSel} onChange={(e) => setOriginSel(e.target.value)}>
              {bases.map((b, i) => <option key={b.name} value={`base:${i}`}>{b.name}</option>)}
            </select>
            <button className="btn btn-primary mt-3 w-full" disabled={!can("route.plan") || !target || busy} onClick={go}>{busy ? "Computing…" : "Find safest route"}</button>
            <ErrorBox error={err} />
          </Panel>
          {res && (
            <Panel title={`Routes to Cell ${String(res.target.cell_no).padStart(2, "0")}`} right={<LevelBadge level={res.target.priority_level} small />}>
              <div className="space-y-2">
                {res.routes.map((r: any) => (
                  <div key={r.kind} className={`rounded border p-2 ${r.recommended ? "border-ok bg-ok/10" : "border-line"}`}>
                    <div className="flex items-center justify-between"><b className="text-xs text-strong">{r.label}</b>{r.recommended && <span className="text-[11px] font-bold text-ok">RECOMMENDED</span>}</div>
                    {r.node_path?.length ? (
                      <div className="mt-1 grid grid-cols-4 gap-1 tabular-nums text-xs">
                        <div><div className="text-[11px]  text-muted">Distance</div>{r.distance_km} km</div>
                        <div><div className="text-[11px]  text-muted">ETA</div>{Math.round(r.eta_min)} min</div>
                        <div><div className="text-[11px]  text-muted">Risk</div>{pct(r.risk)}</div>
                        <div><div className="text-[11px]  text-muted">Blocked</div><span className={r.blocked_segments ? "font-bold text-p1" : ""}>{r.blocked_segments}</span></div>
                      </div>
                    ) : <div className="text-xs text-muted">{r.notes}</div>}
                    {r.segment_names?.length > 0 && <div className="mt-1 text-[11px] text-muted">{r.segment_names.slice(0, 3).join("; ")}</div>}
                  </div>
                ))}
              </div>
              <p className="mt-2 whitespace-pre-line rounded bg-ink p-2 tabular-nums text-xs text-muted">{res.summary}</p>
              {res.last_mile_note && <p className="mt-2 text-xs text-warn">{res.last_mile_note}</p>}
              <p className="mt-2 text-[11px] text-muted">Computed {new Date(res.generated_at).toLocaleTimeString()} from assessment v{res.assessment_version}. ETAs are estimates.</p>
            </Panel>
          )}
        </div>
        <div className="h-[34rem] overflow-hidden rounded border border-line">
          <MapView eventId={Number(id)} data={map} layers={{ ...DEFAULT_LAYERS, hospitals: true, shelters: true, p4: false }} routes={lines} origin={res?.origin} selected={target} highlight={target ? [target] : []} />
        </div>
      </div>
    </div>
  );
}
