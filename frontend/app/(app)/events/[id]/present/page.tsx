"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { LEVEL_COLOR, num } from "@/lib/format";
import { useEvent } from "@/components/EventContext";
import { DEFAULT_LAYERS, LayerState, RouteLine } from "@/components/MapView";
import Pipeline from "@/components/Pipeline";
import { LevelBadge, Spinner } from "@/components/ui";

const MapView = dynamic(() => import("@/components/MapView"), { ssr: false, loading: () => <Spinner /> });
const STEPS = ["Trigger event", "Run analysis", "Show detected change", "Show priority", "Show prediction", "Show route", "Allocate resources", "Simulate field report", "Recalculate"];

export default function Present() {
  const { id } = useParams<{ id: string }>();
  const { event, status, analyse, refresh, busy } = useEvent();
  const version = event?.assessment_version ?? 0;
  const [t, setT] = useState(0);
  const [layers, setLayers] = useState<LayerState>({ ...DEFAULT_LAYERS, p1: false, p2: false, p3: false, p4: false, hazard: false, roads: false, hospitals: false, shelters: false });
  const [routes, setRoutes] = useState<RouteLine[]>([]);
  const [origin, setOrigin] = useState<any>(null);
  const [step, setStep] = useState(-1);
  const [note, setNote] = useState("Press 1 to begin.");
  const [sel, setSel] = useState<string | null>(null);
  const [work, setWork] = useState(false);
  const { data: map } = useApi<any>(`/api/events/${id}/map?t=${t}`, { deps: [version] });
  const { data: k } = useApi<any>(`/api/events/${id}/kpis`, { deps: [version] });
  const L = (p: Partial<LayerState>) => setLayers((l) => ({ ...l, ...p }));
  const stepsNow = useMemo(() => status?.steps ?? [], [status]);

  async function go(i: number) {
    setStep(i); setWork(true);
    try {
      if (i === 0) { setT(0); setRoutes([]); L({ p1: false, p2: false, p3: false, p4: false, hazard: false, roads: false, hospitals: false, shelters: false, satellite: true }); setNote(`${event?.hazard.toUpperCase()} ALERT DETECTED - ${event?.name}. Area ${event?.aoi?.area_km2} km². Simulated post-event SAR shown.`); }
      if (i === 1) { setNote("Running the pipeline: trigger → acquire → prepare → detect → assess → prioritise → predict → plan…"); await analyse(true); }
      if (i === 2) { L({ satellite: true, hazard: true, p1: false, p2: false, p3: false }); const d = (await api(`/api/events/${id}/detections`)).detections[0]; setNote(`CHANGE DETECTED: ${d.area_km2.toFixed(1)} km² · ${d.sensor_mode} · confidence ${(d.mean_confidence * 100).toFixed(0)}%. ${d.sensor_explanation}`); }
      if (i === 3) { L({ satellite: false, hazard: false, p1: true, p2: true, p3: true, roads: true, hospitals: true, shelters: true }); setNote(`PRIORITY: P1 ${k?.levels.P1} · P2 ${k?.levels.P2} · P3 ${k?.levels.P3} · P4 ${k?.levels.P4}. ${num(k?.people_at_risk)} people at high risk.`); }
      if (i === 4) { setT(6); L({ predicted: true }); const p = await api(`/api/events/${id}/predictions`); const h = p.horizons.find((x: any) => x.horizon_h === 6); setNote(`PREDICTION (estimate): P1 ${p.current.P1} → ${h.counts.P1} within 6 h. ${h.p1_new} location(s) likely to escalate. Heuristic model - not guaranteed.`); }
      if (i === 5) {
        setT(0);
        const p1 = (await api(`/api/events/${id}/priorities?level=P1&limit=1`)).cells[0]; setSel(p1.h3_index);
        const r = await api(`/api/events/${id}/routes`, { body: { h3_index: p1.h3_index } });
        setRoutes(r.routes.filter((x: any) => x.node_path?.length).map((x: any) => ({ kind: x.kind, coords: x.coords, recommended: x.recommended, blocked: x.blocked_segments > 0 }))); setOrigin(r.origin);
        setNote(r.summary.split("\n").join("  ·  "));
      }
      if (i === 6) { L({ resources: true }); const a = await api(`/api/events/${id}/resources/optimise`, { body: { commit: true } }); await api(`/api/events/${id}/resources/dispatch`, { body: { reason: "Presentation dispatch" } }); setNote(`RESOURCES: ${a.metrics.units_assigned} units allocated · P1 coverage ${a.metrics.p1_coverage_pct}% · estimated delay ${a.metrics.est_response_delay_min} min.`); }
      if (i === 7) {
        const c = (await api(`/api/events/${id}/priorities?level=P2&limit=1`)).cells[0] || (await api(`/api/events/${id}/priorities?level=P1&limit=1`)).cells[0];
        setSel(c.h3_index);
        const r = await api(`/api/events/${id}/field-reports/simulate`, { body: { h3_index: c.h3_index, verdict: "severe", kind: "flood" } });
        setNote(`FIELD VERIFIED (simulated): Cell ${String(r.cell_no).padStart(2, "0")} ${r.before.level} → ${r.after.level}. Photo: ${r.photo_analysis[0]?.detected.join(", ") || "n/a"} (heuristic).`);
      }
      if (i === 8) { setRoutes([]); setNote(`RECALCULATED: P1 now ${(await api(`/api/events/${id}/kpis`)).levels.P1}. Closed loop: Detect → Respond → Verify → Recalculate.`); }
      refresh();
    } catch (e: any) { setNote(`Error: ${e.message}`); } finally { setWork(false); }
  }

  return (
    <div className="present grid h-screen grid-cols-[22rem_1fr] bg-ink">
      <aside className="flex min-h-0 flex-col border-r border-line bg-panel p-4">
        <div className="mb-1 flex items-center gap-2"><span className="pulse-dot inline-block h-2.5 w-2.5 rounded-full bg-p1" /><span className="text-xs font-bold   text-p1">Live DISHA demonstration</span></div>
        <div className="tabular-nums text-3xl font-bold  text-strong">DISHA</div>
        <div className="mb-3 text-xs text-muted">{event?.name} · <span className="text-warn">DEMONSTRATION DATA</span></div>
        <div className="space-y-1.5 overflow-y-auto">
          {STEPS.map((s, i) => (
            <button key={s} disabled={work || busy || (i > 1 && !version)} onClick={() => go(i)} className={`flex w-full items-center gap-3 rounded border px-3 py-2.5 text-left text-sm font-semibold transition disabled:opacity-40 ${step === i ? "border-accent bg-accent/15 text-strong" : "border-line text-text hover:border-muted"}`}>
              <span className="tabular-nums text-lg text-accent">{i + 1}</span>{s}
            </button>
          ))}
        </div>
        <div className="mt-3 rounded border border-line bg-ink p-3 text-[13px] leading-snug text-text">{work || busy ? <span className="pulse-dot text-accent">● working…</span> : note}</div>
        <div className="mt-3 hidden xl:block"><Pipeline steps={stepsNow} compact /></div>
        <Link href={`/events/${id}/map`} className="btn mt-auto">Exit presentation</Link>
      </aside>
      <main className="relative min-h-0">
        {version > 0 || step === 0 ? <MapView eventId={Number(id)} data={map} layers={layers} routes={routes} origin={origin} selected={sel} onSelect={setSel} /> : <div className="grid h-full place-items-center text-muted">Press 2 to run the analysis.</div>}
        {k && version > 0 && (
          <div className="absolute left-4 top-4 flex gap-6 rounded border border-line bg-panel/95 px-4 py-2">
            {(["P1", "P2", "P3", "P4"] as const).map((l) => <div key={l} className="text-center"><div className="tabular-nums text-3xl font-bold" style={{ color: LEVEL_COLOR[l] }}>{map?.counts?.[l] ?? k.levels[l]}</div><div className="text-[11px] font-bold text-muted">{l}</div></div>)}
            {t > 0 && <span className="self-center rounded bg-accent/20 px-2 py-1 text-xs font-bold text-accent">ESTIMATE +{t}h</span>}
          </div>
        )}
        {sel && map && <div className="absolute bottom-4 right-4"><LevelBadge level={map.cells.features.find((f: any) => f.properties.h3_index === sel)?.properties.display_level || "P4"} /></div>}
      </main>
    </div>
  );
}
