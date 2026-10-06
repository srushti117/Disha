"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { LEVEL_COLOR } from "@/lib/format";
import CellPanel from "./CellPanel";
import { DEFAULT_LAYERS, LayerState, RouteLine } from "./MapView";
import { DemoBadge, RealBadge, Spinner, Toggle } from "./ui";
import { useEvent } from "./EventContext";

const MapView = dynamic(() => import("./MapView"), { ssr: false, loading: () => <Spinner text="Loading map…" /> });

const STOPS = [
  { t: -1, label: "Before event" }, { t: 0, label: "Now" }, { t: 6, label: "+6 h" }, { t: 12, label: "+12 h" }, { t: 24, label: "+24 h" }, { t: 48, label: "+48 h" },
];

export const LAYER_GROUPS: { title: string; items: { key: keyof LayerState; label: string; color?: string }[] }[] = [
  { title: "Imagery & detection", items: [
    { key: "optical", label: "Sentinel-2 true colour (post-event)" }, { key: "satellite", label: "Radar (SAR) post-event" }, { key: "sarPre", label: "Radar (SAR) pre-event" },
    { key: "hazard", label: "Hazard detection", color: "#3b9eff" }, { key: "severity", label: "Severity", color: "#eb6e28" }, { key: "confidence", label: "Detection confidence", color: "#35c28a" } ] },
  { title: "Priority", items: [
    { key: "p1", label: "P1 Critical", color: LEVEL_COLOR.P1 }, { key: "p2", label: "P2 High", color: LEVEL_COLOR.P2 },
    { key: "p3", label: "P3 Moderate", color: LEVEL_COLOR.P3 }, { key: "p4", label: "P4 Low", color: LEVEL_COLOR.P4 }, { key: "predicted", label: "Predicted risk (time slider)", color: "#9b8cff" } ] },
  { title: "People", items: [{ key: "population", label: "Population (estimate)", color: "#c8508f" }, { key: "vulnerability", label: "Vulnerability (est.)", color: "#dc5aa0" }] },
  { title: "Infrastructure & response", items: [
    { key: "roads", label: "Roads (status)" }, { key: "hospitals", label: "Hospitals", color: "#ff5d73" }, { key: "schools", label: "Schools", color: "#f2c744" },
    { key: "otherInfra", label: "Power / water / bridges", color: "#9b8cff" }, { key: "shelters", label: "Shelters", color: "#35c28a" }, { key: "resources", label: "Rescue teams & units", color: "#3b9eff" } ] },
];

export default function MapWorkspace({ eventId, initialLayers, hideLayerPanel, extraLeft, selectedExternal }: {
  eventId: number; initialLayers?: Partial<LayerState>; hideLayerPanel?: boolean; extraLeft?: React.ReactNode; selectedExternal?: string | null;
}) {
  const { can } = useAuth();
  const { event } = useEvent();
  const [layers, setLayers] = useState<LayerState>({ ...DEFAULT_LAYERS, ...initialLayers });
  const [t, setT] = useState(0);
  const [selected, setSelected] = useState<string | null>(selectedExternal ?? null);
  const [routes, setRoutes] = useState<RouteLine[]>([]);
  const [origin, setOrigin] = useState<any>(null);
  const [online, setOnline] = useState(!!(event && !event.is_demo));
  const [light, setLight] = useState(true);
  const [panelOpen, setPanelOpen] = useState(true);
  const version = event?.assessment_version ?? 0;
  const { data, loading, error } = useApi<any>(`/api/events/${eventId}/map?t=${t}`, { deps: [version] });

  useEffect(() => { if (selectedExternal) setSelected(selectedExternal); }, [selectedExternal]);
  useEffect(() => { if (event && !event.is_demo) { setOnline(true); setLayers((l) => (data?.layers?.some((x: any) => x.key === "optical") ? l : l)); } }, [event?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setLayers((l) => (t > 0 ? { ...l, predicted: true } : l)); }, [t]);
  const set = (k: keyof LayerState) => (v: boolean) => setLayers((l) => ({ ...l, [k]: v }));

  return (
    <div className="relative h-full w-full overflow-hidden rounded border border-line bg-ink">
      <MapView eventId={eventId} data={data} layers={layers} selected={selected} onSelect={setSelected} routes={routes} origin={origin} online={online} light={light} />
      {error && <div className="absolute left-1/2 top-3 -translate-x-1/2 rounded border border-p1/50 bg-ink/90 px-3 py-1.5 text-xs text-p1">{error}</div>}
      {loading && !data && <div className="absolute inset-0 flex items-center justify-center"><Spinner text="Loading digital twin…" /></div>}

      <div className="pointer-events-none absolute left-3 top-3 flex max-h-[calc(100%-6.5rem)] flex-col gap-2">
        {!hideLayerPanel && (
          <div className="pointer-events-auto panel flex max-h-full w-56 flex-col overflow-hidden bg-panel/95">
            <button className="flex items-center justify-between border-b border-line px-3 py-2 text-xs font-bold   text-muted" onClick={() => setPanelOpen((o) => !o)}>
              Layers <span>{panelOpen ? "−" : "+"}</span>
            </button>
            {panelOpen && (
              <div className="overflow-y-auto p-2">
                {LAYER_GROUPS.map((g) => (
                  <div key={g.title} className="mb-2">
                    <div className="px-1.5 text-[11px] font-bold   text-muted/70">{g.title}</div>
                    {g.items.map((i) => <Toggle key={i.key} on={layers[i.key]} onChange={set(i.key)} label={i.label} color={i.color} />)}
                  </div>
                ))}
                <div className="border-t border-line pt-2">
                  <Toggle on={light} onChange={setLight} label="Light map mode (off = dark)" />
                  <Toggle on={online} onChange={setOnline} label="Online basemap (needs internet)" />
                </div>
              </div>
            )}
          </div>
        )}
        {extraLeft}
      </div>

      {data && (
        <div className="pointer-events-none absolute left-1/2 top-3 flex -translate-x-1/2 items-center gap-2 rounded border border-line bg-panel/95 px-3 py-1.5">
          {(["P1", "P2", "P3", "P4"] as const).map((l) => (
            <span key={l} className="flex items-center gap-1 text-xs font-bold" style={{ color: LEVEL_COLOR[l] }}>
              <span className="inline-block h-2 w-2 rounded-sm" style={{ background: LEVEL_COLOR[l] }} />{l} <span className="tabular-nums text-strong">{data.counts[l]}</span>
            </span>
          ))}
          {event?.is_demo && <DemoBadge className="ml-2" />}
          {event && !event.is_demo && <RealBadge className="ml-2" />}
          {t > 0 && <span className="ml-1 rounded bg-accent/20 px-1.5 py-0.5 text-[11px] font-bold text-accent">ESTIMATE +{t}h</span>}
          {t === -1 && <span className="ml-1 rounded bg-muted/20 px-1.5 py-0.5 text-[11px] font-bold text-muted">PRE-EVENT</span>}
        </div>
      )}

      {routes.length > 0 && (
        <button className="btn btn-sm absolute right-14 top-3" onClick={() => { setRoutes([]); setOrigin(null); }}>Clear routes</button>
      )}

      {selected && (
        <div className="absolute bottom-16 right-3 top-3 z-10 flex max-h-full">
          <CellPanel eventId={eventId} h3={selected} version={version} onClose={() => setSelected(null)} canPlan={can("route.plan")} canAssign={can("resource.assign")} canField={can("field.report")}
            onRoutes={(r, o) => { setRoutes(r); setOrigin(o); }} onTime={(x) => setT(x)} />
        </div>
      )}

      <div className="absolute bottom-3 left-3 right-3 rounded border border-line bg-panel/95 px-4 py-2">
        <div className="mb-1 flex items-center justify-between text-[11px] font-bold   text-muted">
          <span>Time slider</span>
          <span>{t > 0 ? "Heuristic estimates - uncalibrated, not guaranteed" : t === -1 ? "Before event" : "Current assessed state"}</span>
        </div>
        <input type="range" min={0} max={STOPS.length - 1} step={1} value={STOPS.findIndex((s) => s.t === t)} onChange={(e) => setT(STOPS[Number(e.target.value)].t)} className="w-full accent-accent" aria-label="Time machine" />
        <div className="flex justify-between">
          {STOPS.map((s) => (
            <button key={s.t} onClick={() => setT(s.t)} className={`text-[11px] font-semibold ${s.t === t ? "text-accent" : "text-muted hover:text-text"}`}>{s.label}</button>
          ))}
        </div>
      </div>
    </div>
  );
}
