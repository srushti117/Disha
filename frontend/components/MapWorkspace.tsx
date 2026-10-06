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

const STOPS = [{ t: -1, label: "Before" }, { t: 0, label: "Now" }, { t: 6, label: "+6 h" }, { t: 12, label: "+12 h" }, { t: 24, label: "+24 h" }, { t: 48, label: "+48 h" }];

/** Rarely needed layers, kept out of the way. */
const MORE: { key: keyof LayerState; label: string }[] = [
  { key: "sarPre", label: "Radar before the event" }, { key: "severity", label: "Severity colouring" }, { key: "confidence", label: "Detection confidence" }, { key: "p4", label: "Low-priority areas (P4)" },
  { key: "predicted", label: "Predicted spread" }, { key: "population", label: "Population density" }, { key: "vulnerability", label: "Vulnerability" }, { key: "schools", label: "Schools" },
  { key: "otherInfra", label: "Power, water, bridges" }, { key: "resources", label: "Rescue units" },
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
  const hasOptical = !!data?.layers?.some((x: any) => x.key === "optical");

  useEffect(() => { if (selectedExternal) setSelected(selectedExternal); }, [selectedExternal]);
  useEffect(() => { if (event && !event.is_demo) setOnline(true); }, [event?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setLayers((l) => (t > 0 ? { ...l, predicted: true } : l)); }, [t]);
  const set = (k: keyof LayerState) => (v: boolean) => setLayers((l) => ({ ...l, [k]: v }));
  const imageKey: keyof LayerState = hasOptical ? "optical" : "satellite";
  const priorityOn = layers.p1 && layers.p2 && layers.p3;

  return (
    <div className="relative h-full w-full overflow-hidden rounded-lg border border-line bg-ink">
      <MapView eventId={eventId} data={data} layers={layers} selected={selected} onSelect={setSelected} routes={routes} origin={origin} online={online} light={light} />
      {error && <div className="absolute left-1/2 top-3 -translate-x-1/2 rounded border border-p1/50 bg-panel px-3 py-1.5 text-sm text-p1">{error}</div>}
      {loading && !data && <div className="absolute inset-0 flex items-center justify-center"><Spinner text="Loading map…" /></div>}

      <div className="pointer-events-none absolute left-3 top-3 flex max-h-[calc(100%-5.5rem)] flex-col gap-2">
        {!hideLayerPanel && (
          <div className="pointer-events-auto panel flex max-h-full w-60 flex-col overflow-hidden bg-panel/95">
            <button className="flex items-center justify-between px-3.5 py-2.5 text-sm font-semibold text-strong" onClick={() => setPanelOpen((o) => !o)}>
              Layers <span className="text-muted">{panelOpen ? "−" : "+"}</span>
            </button>
            {panelOpen && (
              <div className="overflow-y-auto border-t border-line px-2 py-2">
                <Toggle on={layers[imageKey]} onChange={set(imageKey)} label={hasOptical ? "Satellite image" : "Radar image"} />
                <Toggle on={layers.hazard} onChange={set("hazard")} label="Detected hazard" color="#1d6fd8" />
                <Toggle on={priorityOn} onChange={(v) => setLayers((l) => ({ ...l, p1: v, p2: v, p3: v }))} label="Priority areas" color={LEVEL_COLOR.P1} />
                <Toggle on={layers.roads} onChange={set("roads")} label="Roads" />
                <Toggle on={layers.hospitals} onChange={set("hospitals")} label="Hospitals" color="#d6455b" />
                <Toggle on={layers.shelters} onChange={set("shelters")} label="Shelters" color="#1f9d6b" />
                <details className="mt-1 border-t border-line pt-1">
                  <summary className="cursor-pointer list-none rounded px-1.5 py-1.5 text-sm text-muted hover:text-strong [&::-webkit-details-marker]:hidden">More layers…</summary>
                  <div className="pb-1">
                    {MORE.map((m) => <Toggle key={m.key} on={layers[m.key]} onChange={set(m.key)} label={m.label} />)}
                    <div className="mt-1 border-t border-line pt-1">
                      <Toggle on={online} onChange={setOnline} label="Street map (needs internet)" />
                      <Toggle on={light} onChange={setLight} label="Light background" />
                    </div>
                  </div>
                </details>
              </div>
            )}
          </div>
        )}
        {extraLeft}
      </div>

      {data && (
        <div className="pointer-events-none absolute left-1/2 top-3 flex -translate-x-1/2 items-center gap-3 rounded-full border border-line bg-panel/95 px-4 py-1.5 shadow-sm">
          {(["P1", "P2", "P3"] as const).map((l) => (
            <span key={l} className="flex items-center gap-1.5 text-sm font-medium" style={{ color: LEVEL_COLOR[l] }}>
              <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: LEVEL_COLOR[l] }} />{l} <span className="tabular-nums text-strong">{data.counts[l]}</span>
            </span>
          ))}
          {event?.is_demo ? <DemoBadge /> : <RealBadge />}
        </div>
      )}

      {routes.length > 0 && <button className="btn btn-sm absolute right-14 top-3 bg-panel" onClick={() => { setRoutes([]); setOrigin(null); }}>Clear routes</button>}

      {selected && (
        <div className="absolute bottom-16 right-3 top-3 z-10 flex max-h-full">
          <CellPanel eventId={eventId} h3={selected} version={version} onClose={() => setSelected(null)} canPlan={can("route.plan")} canAssign={can("resource.assign")} canField={can("field.report")}
            onRoutes={(r, o) => { setRoutes(r); setOrigin(o); }} onTime={(x) => setT(x)} />
        </div>
      )}

      <div className="absolute bottom-3 left-3 flex items-center gap-3 rounded-full border border-line bg-panel/95 px-3 py-1.5 shadow-sm">
        <span className="text-sm text-muted">Time</span>
        <div className="flex gap-0.5" role="group" aria-label="Time">
          {STOPS.map((s) => (
            <button key={s.t} onClick={() => setT(s.t)} className={`rounded-full px-2.5 py-1 text-sm ${s.t === t ? "bg-accent font-medium text-white" : "text-muted hover:text-strong"}`}>{s.label}</button>
          ))}
        </div>
        {t > 0 && <span className="pr-1 text-xs font-medium text-accent">ESTIMATE +{t}h · not guaranteed</span>}
        {t === -1 && <span className="pr-1 text-xs text-muted">before the event</span>}
      </div>
    </div>
  );
}
