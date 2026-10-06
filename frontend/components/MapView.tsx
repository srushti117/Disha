"use client";
import { useEffect, useMemo, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { BitmapLayer, GeoJsonLayer, PathLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { authedUrl } from "@/lib/api";
import { LEVEL_COLOR, hexToRgb } from "@/lib/format";

export type LayerState = {
  satellite: boolean; optical: boolean; sarPre: boolean; hazard: boolean; confidence: boolean; severity: boolean;
  p1: boolean; p2: boolean; p3: boolean; p4: boolean;
  population: boolean; vulnerability: boolean; roads: boolean; hospitals: boolean; schools: boolean; otherInfra: boolean;
  shelters: boolean; resources: boolean; predicted: boolean;
};
export const DEFAULT_LAYERS: LayerState = {
  satellite: false, optical: false, sarPre: false, hazard: true, confidence: false, severity: false, p1: true, p2: true, p3: true, p4: false,
  population: false, vulnerability: false, roads: true, hospitals: true, schools: false, otherInfra: false, shelters: true, resources: false, predicted: false,
};

export type RouteLine = { kind: string; coords: number[][]; recommended?: boolean; blocked?: boolean; label?: string };

type Props = {
  eventId: number;
  data: any | null;
  layers: LayerState;
  selected?: string | null;
  onSelect?: (h3: string | null) => void;
  routes?: RouteLine[];
  origin?: { lat: number; lon: number } | null;
  online?: boolean;
  light?: boolean;
  highlight?: string[];
  hazard?: string;
};

const INFRA_COLOR: Record<string, [number, number, number]> = {
  hospital: [255, 93, 115], school: [242, 199, 68], power: [155, 140, 255], water: [59, 201, 219], bridge: [200, 165, 120], emergency: [255, 159, 28], comm: [173, 181, 189],
};
const RES_COLOR: Record<string, [number, number, number]> = {
  rescue_team: [53, 194, 138], ambulance: [255, 93, 115], boat: [59, 158, 255], medical_team: [255, 140, 200], drone: [190, 160, 255], relief_vehicle: [242, 199, 68],
};
const ROAD_COLOR: Record<string, [number, number, number]> = {
  open: [90, 108, 135], potentially_blocked: [255, 176, 32], blocked: [255, 59, 59], unknown: [120, 120, 150],
};

function ramp(v: number, stops: [number, number, number][]): [number, number, number] {
  const x = Math.max(0, Math.min(0.999, v)) * (stops.length - 1);
  const i = Math.floor(x), f = x - i;
  const a = stops[i], b = stops[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}
const SEV_RAMP: [number, number, number][] = [[40, 90, 160], [60, 180, 200], [250, 220, 90], [235, 110, 40], [200, 30, 40]];
const VULN_RAMP: [number, number, number][] = [[30, 40, 80], [120, 70, 170], [220, 90, 160], [255, 200, 120]];

function centroid(f: any): [number, number] {
  const ring = f.geometry.coordinates[0];
  let x = 0, y = 0;
  for (const p of ring) { x += p[0]; y += p[1]; }
  return [x / ring.length, y / ring.length];
}

export default function MapView({ eventId, data, layers, selected, onSelect, routes, origin, online, light = true, highlight, hazard }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const fitted = useRef<string | null>(null);
  const readyRef = useRef(false);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!el.current) return;
    const map = new maplibregl.Map({
      container: el.current,
      style: { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#dfe6ee" } }] },
      center: [78, 20], zoom: 4, attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    const overlay = new MapboxOverlay({ interleaved: false, layers: [] });
    map.on("load", () => {
      map.addControl(overlay as any);
      readyRef.current = true;
      (map as any)._reapply?.();
    });
    mapRef.current = map;
    overlayRef.current = overlay;
    return () => {
      readyRef.current = false;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // basemap mode (dark/light background, optional online tiles)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      map.setPaintProperty("bg", "background-color", light ? "#dfe6ee" : "#0a111c");
      if (map.getLayer("osm")) map.removeLayer("osm");
      if (map.getSource("osm")) map.removeSource("osm");
      if (online) {
        map.addSource("osm", { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 19, attribution: "© OpenStreetMap contributors (online basemap)" });
        map.addLayer({ id: "osm", type: "raster", source: "osm", paint: { "raster-opacity": light ? 1 : 0.5, "raster-saturation": light ? 0 : -0.85, "raster-brightness-max": light ? 1 : 0.6 } }, undefined);
      }
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [online, light]);

  const bounds = data?.bounds as number[] | undefined;
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !bounds) return;
    const key = `${eventId}:${bounds.join(",")}`;
    if (fitted.current === key) return;
    fitted.current = key;
    map.fitBounds([[bounds[0], bounds[1]], [bounds[2], bounds[3]]], { padding: 40, duration: 0 });
  }, [bounds, eventId]);

  const deckLayers = useMemo(() => {
    if (!data) return [];
    const out: any[] = [];
    const b = data.bounds as number[] | undefined;
    const imageLayer = (key: string, opacity: number) =>
      b && new BitmapLayer({ id: `img-${key}`, image: authedUrl(`/api/events/${eventId}/layers/${key}.png`), bounds: [b[0], b[1], b[2], b[3]], opacity, pickable: false });
    if (layers.optical) out.push(imageLayer("optical", 1));
    if (layers.satellite) out.push(imageLayer("sar_post", 0.95));
    if (layers.sarPre) out.push(imageLayer("sar_pre", 0.95));
    if (layers.population) out.push(imageLayer("population", 0.8));
    if (layers.confidence) out.push(imageLayer("confidence", 0.85));
    if (layers.hazard) out.push(imageLayer("hazard", 0.8));
    const feats: any[] = data.cells.features;
    const cellData = data.cells;
    const lvlOn: Record<string, boolean> = { P1: layers.p1, P2: layers.p2, P3: layers.p3, P4: layers.p4 };
    if (layers.severity) {
      out.push(new GeoJsonLayer({ id: "cells-sev", data: cellData, pickable: false, stroked: false, filled: true,
        getFillColor: (f: any) => { const s = f.properties.display_severity; return s < 0.03 ? [0, 0, 0, 0] : [...ramp(s, SEV_RAMP), 190]; }, updateTriggers: { getFillColor: [data.time] } }));
    }
    if (layers.vulnerability) {
      out.push(new GeoJsonLayer({ id: "cells-vuln", data: cellData, pickable: false, stroked: false, filled: true,
        getFillColor: (f: any) => [...ramp(f.properties.vulnerability_score, VULN_RAMP), f.properties.population > 0 ? 180 : 0] }));
    }
    out.push(new GeoJsonLayer({
      id: "cells", data: cellData, pickable: true, stroked: true, filled: true, lineWidthUnits: "pixels", autoHighlight: true, highlightColor: [255, 255, 255, 60],
      getFillColor: (f: any) => {
        const l = f.properties.display_level as string;
        if (!lvlOn[l]) return [0, 0, 0, layers.severity || layers.vulnerability ? 0 : 6];
        const c = hexToRgb(LEVEL_COLOR[l]);
        if (layers.severity || layers.vulnerability) return [c[0], c[1], c[2], 40];
        return [c[0], c[1], c[2], l === "P4" ? 40 : l === "P3" ? 110 : 150];
      },
      getLineColor: (f: any) => (f.properties.h3_index === selected ? [255, 255, 255, 255] : (highlight || []).includes(f.properties.h3_index) ? [90, 200, 255, 255] : light ? [70, 90, 120, 120] : [60, 85, 125, 110]),
      getLineWidth: (f: any) => (f.properties.h3_index === selected ? 3 : (highlight || []).includes(f.properties.h3_index) ? 2.5 : 0.6),
      updateTriggers: { getFillColor: [layers.p1, layers.p2, layers.p3, layers.p4, layers.severity, layers.vulnerability, data.time, data.event?.assessment_version], getLineColor: [selected, highlight, light], getLineWidth: [selected, highlight] },
      onClick: (info: any) => onSelectRef.current?.(info.object ? info.object.properties.h3_index : null),
    }));
    if (layers.predicted && data.time > 0) {
      out.push(new ScatterplotLayer({ id: "pred", data: feats.filter((f) => (f.properties.probability ?? 0) >= 0.35), pickable: false, radiusUnits: "meters", stroked: true, filled: false, lineWidthUnits: "pixels",
        getPosition: (f: any) => centroid(f), getRadius: (f: any) => 120 + 260 * f.properties.probability, getLineWidth: 1.5, getLineColor: (f: any) => [...hexToRgb(LEVEL_COLOR[f.properties.display_level]), 230] }));
    }
    if (layers.roads) {
      out.push(new GeoJsonLayer({ id: "roads", data: data.roads, pickable: true, stroked: false, filled: false, lineWidthUnits: "pixels", lineCapRounded: true,
        getLineColor: (f: any) => [...ROAD_COLOR[f.properties.status], f.properties.status === "open" ? 150 : 255],
        getLineWidth: (f: any) => (f.properties.status === "blocked" ? 4 : f.properties.status === "potentially_blocked" ? 3 : f.properties.class === "primary" ? 2 : 1.2) }));
    }
    const infra = data.infrastructure.features.filter((f: any) => {
      const k = f.properties.kind;
      return (k === "hospital" && layers.hospitals) || (k === "school" && layers.schools) || (!["hospital", "school"].includes(k) && layers.otherInfra);
    });
    if (infra.length) {
      out.push(new ScatterplotLayer({ id: "infra", data: infra, pickable: true, radiusUnits: "pixels", stroked: true, lineWidthUnits: "pixels", getPosition: (f: any) => f.geometry.coordinates,
        getRadius: (f: any) => (f.properties.kind === "hospital" ? 8 : 5.5), getFillColor: (f: any) => [...INFRA_COLOR[f.properties.kind] || [200, 200, 200], 255],
        getLineColor: (f: any) => (f.properties.risk >= 0.25 ? [255, 255, 255, 255] : [8, 13, 21, 255]), getLineWidth: (f: any) => (f.properties.risk >= 0.25 ? 2.5 : 1) }));
    }
    if (layers.shelters) {
      out.push(new ScatterplotLayer({ id: "shelters", data: data.shelters.features, pickable: true, radiusUnits: "pixels", stroked: true, lineWidthUnits: "pixels", getPosition: (f: any) => f.geometry.coordinates,
        getRadius: 7, getFillColor: (f: any) => (f.properties.in_hazard_zone ? [229, 72, 77, 220] : [53, 194, 138, 230]), getLineColor: [255, 255, 255, 255], getLineWidth: 1.5 }));
    }
    if (layers.resources) {
      out.push(new ScatterplotLayer({ id: "resources", data: data.resources.features, pickable: true, radiusUnits: "pixels", stroked: true, lineWidthUnits: "pixels", getPosition: (f: any) => f.geometry.coordinates,
        getRadius: 5, getFillColor: (f: any) => [...(RES_COLOR[f.properties.kind] || [200, 200, 200]), f.properties.status === "deployed" ? 255 : 150], getLineColor: [255, 255, 255, 200], getLineWidth: 1 }));
    }
    if (routes?.length) {
      out.push(new PathLayer({ id: "routes", data: routes, pickable: false, widthUnits: "pixels", capRounded: true, jointRounded: true, getPath: (r: RouteLine) => r.coords as any,
        getColor: (r: RouteLine) => (r.blocked ? [255, 59, 59, 230] : r.kind === "safest" ? [53, 194, 138, 255] : r.kind === "fastest" ? [59, 158, 255, 255] : [200, 210, 225, 220]),
        getWidth: (r: RouteLine) => (r.recommended ? 7 : 3.5) }));
    }
    if (origin) {
      out.push(new ScatterplotLayer({ id: "origin", data: [origin], radiusUnits: "pixels", getPosition: (o: any) => [o.lon, o.lat], getRadius: 9, getFillColor: [59, 158, 255, 255], stroked: true, getLineColor: [255, 255, 255, 255], lineWidthUnits: "pixels", getLineWidth: 2 }));
    }
    const p1 = feats.filter((f) => f.properties.display_level === "P1" && layers.p1);
    if (p1.length && p1.length < 80) {
      out.push(new TextLayer({ id: "labels", data: p1, getPosition: (f: any) => centroid(f), getText: (f: any) => String(f.properties.cell_no).padStart(2, "0"), getSize: 12, getColor: [255, 255, 255, 255],
        fontWeight: 700, outlineWidth: 2, outlineColor: [8, 13, 21, 255], fontSettings: { sdf: true }, pickable: false }));
    }
    return out.filter(Boolean);
  }, [data, layers, selected, routes, origin, eventId, highlight, light]);

  useEffect(() => {
    const apply = () => overlayRef.current?.setProps({
      layers: deckLayers,
      getTooltip: ({ object, layer }: any) => {
        if (!object) return null;
        const p = object.properties || {};
        const style = { backgroundColor: "#ffffff", color: "#24344a", border: "1px solid #d3dce8", boxShadow: "0 2px 8px rgba(0,0,0,.15)", fontSize: "11px", padding: "6px 8px", borderRadius: "4px" };
        if (layer?.id === "cells") return { html: `<b>Cell ${String(p.cell_no).padStart(2, "0")}</b> · ${p.display_level} · score ${Number(p.display_score).toFixed(2)}<br/>Severity ${(p.display_severity * 100).toFixed(0)}% · ${Number(p.population_exposed).toLocaleString()} exposed${p.probability ? `<br/>Estimated probability ${(p.probability * 100).toFixed(0)}%` : ""}`, style };
        if (layer?.id === "roads") return { html: `<b>${p.name}</b><br/>${String(p.status).replace("_", " ")}${p.is_bridge ? " · bridge" : ""}`, style };
        if (layer?.id === "infra") return { html: `<b>${p.name}</b><br/>${p.kind} · ${p.status}${p.risk >= 0.25 ? ` · risk ${(p.risk * 100).toFixed(0)}%` : ""}`, style };
        if (layer?.id === "shelters") return { html: `<b>${p.name}</b><br/>capacity ${p.capacity}${p.in_hazard_zone ? " · IN HAZARD ZONE" : ""}`, style };
        if (layer?.id === "resources") return { html: `<b>${p.name}</b><br/>${p.status}`, style };
        return null;
      },
    } as any);
    if (readyRef.current) apply();
    else if (mapRef.current) (mapRef.current as any)._reapply = apply;
  }, [deckLayers]);

  return <div ref={el} className="h-full w-full" data-testid="map" />;
}
