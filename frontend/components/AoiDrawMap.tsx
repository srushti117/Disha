"use client";
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

export default function AoiDrawMap({ points, onChange, online }: { points: [number, number][]; onChange: (p: [number, number][]) => void; online: boolean }) {
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const ptsRef = useRef(points);
  ptsRef.current = points;
  const cbRef = useRef(onChange);
  cbRef.current = onChange;

  useEffect(() => {
    if (!el.current) return;
    const map = new maplibregl.Map({
      container: el.current, center: [76.33, 10.3], zoom: 8,
      style: { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#dfe6ee" } }] },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      map.addSource("aoi", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "aoi-fill", type: "fill", source: "aoi", paint: { "fill-color": "#3b9eff", "fill-opacity": 0.2 } });
      map.addLayer({ id: "aoi-line", type: "line", source: "aoi", paint: { "line-color": "#3b9eff", "line-width": 2 } });
      map.addLayer({ id: "aoi-pt", type: "circle", source: "aoi", filter: ["==", "$type", "Point"], paint: { "circle-radius": 5, "circle-color": "#fff", "circle-stroke-color": "#3b9eff", "circle-stroke-width": 2 } });
      map.on("click", (e) => cbRef.current([...ptsRef.current, [e.lngLat.lng, e.lngLat.lat]]));
      map.getCanvas().style.cursor = "crosshair";
    });
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      if (map.getLayer("osm")) map.removeLayer("osm");
      if (map.getSource("osm")) map.removeSource("osm");
      if (online) {
        map.addSource("osm", { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap contributors" });
        map.addLayer({ id: "osm", type: "raster", source: "osm", paint: { "raster-opacity": 0.6 } }, map.getLayer("aoi-fill") ? "aoi-fill" : undefined);
      }
    };
    if (map.isStyleLoaded()) apply(); else map.once("load", apply);
  }, [online]);

  useEffect(() => {
    const map = mapRef.current;
    const upd = () => {
      const src = map?.getSource("aoi") as maplibregl.GeoJSONSource | undefined;
      if (!src) return;
      const feats: any[] = points.map((p) => ({ type: "Feature", geometry: { type: "Point", coordinates: p }, properties: {} }));
      if (points.length >= 3) feats.push({ type: "Feature", geometry: { type: "Polygon", coordinates: [[...points, points[0]]] }, properties: {} });
      else if (points.length === 2) feats.push({ type: "Feature", geometry: { type: "LineString", coordinates: points }, properties: {} });
      src.setData({ type: "FeatureCollection", features: feats });
    };
    if (map?.isStyleLoaded()) upd(); else map?.once("load", upd);
  }, [points]);

  return <div ref={el} className="h-72 w-full rounded border border-line" />;
}
