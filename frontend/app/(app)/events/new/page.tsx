"use client";
import dynamic from "next/dynamic";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ErrorBox, PageHeader, Panel, Tabs } from "@/components/ui";

const AoiDrawMap = dynamic(() => import("@/components/AoiDrawMap"), { ssr: false });
type Method = "demo" | "draw" | "coordinates" | "admin" | "upload";

export default function NewEvent() {
  const router = useRouter();
  const { data: sc } = useApi<any>("/api/scenarios");
  const [method, setMethod] = useState<Method>("demo");
  const [dataMode, setDataMode] = useState<"simulated" | "live">("live");
  const [dates, setDates] = useState({ pre_end: "2018-08-12", post_start: "2018-08-17", post_end: "2018-09-10" });
  const [name, setName] = useState("");
  const [hazard, setHazard] = useState("flood");
  const [res, setRes] = useState(8);
  const [scenario, setScenario] = useState("kerala_kuttanad_2018");
  const [pts, setPts] = useState<[number, number][]>([]);
  const [online, setOnline] = useState(false);
  const [coords, setCoords] = useState({ west: "76.27", south: "10.25", east: "76.39", north: "10.35" });
  const [admin, setAdmin] = useState("ernakulam");
  const [geojson, setGeojson] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    let aoi: any = {};
    let body: any = { name, hazard, aoi_method: method, h3_resolution: res };
    if (method === "demo") body = { ...body, scenario_key: scenario, hazard: sc.scenarios.find((s: any) => s.key === scenario)?.hazard || hazard };
    else if (dataMode === "live") body = { ...body, data_mode: "live", live: { ...dates } };
    if (method === "draw") {
      if (pts.length < 3) return setErr("Click at least 3 points on the map to draw a polygon.");
      aoi = { geojson: { type: "Polygon", coordinates: [[...pts, pts[0]]] } };
    }
    if (method === "coordinates") aoi = { west: +coords.west, south: +coords.south, east: +coords.east, north: +coords.north };
    if (method === "admin") aoi = { admin_id: admin };
    if (method === "upload") {
      try { aoi = { geojson: JSON.parse(geojson) }; } catch { return setErr("The uploaded text is not valid JSON."); }
    }
    setBusy(true);
    try {
      const ev = await api("/api/events", { body: { ...body, aoi } });
      router.push(`/events/${ev.id}`);
    } catch (ex: any) { setErr(ex.message); } finally { setBusy(false); }
  }

  function onFile(f: File | undefined) {
    if (!f) return;
    const r = new FileReader();
    r.onload = () => setGeojson(String(r.result));
    r.readAsText(f);
  }

  return (
    <div className="mx-auto max-w-3xl p-4">
      <PageHeader title="New event" sub="Define the hazard and the area of interest (AOI)" />
      <form onSubmit={submit} className="space-y-4">
        <Panel title="Event">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="md:col-span-2"><label className="label" htmlFor="n">Name</label><input id="n" className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Optional - defaults to the scenario name" /></div>
            <div><label className="label" htmlFor="h">Hazard type</label>
              <select id="h" className="input" value={hazard} onChange={(e) => setHazard(e.target.value)} disabled={method === "demo"}>
                <option value="flood">Flood</option><option value="wildfire">Wildfire</option><option value="landslide">Landslide</option><option value="cyclone">Cyclone</option>
              </select></div>
            <div><label className="label" htmlFor="r">H3 resolution</label>
              <select id="r" className="input" value={res} onChange={(e) => setRes(+e.target.value)}>
                {[7, 8, 9].map((r) => <option key={r} value={r}>{r} - {r === 7 ? "~1.2 km" : r === 8 ? "~460 m (default)" : "~175 m"} edge</option>)}
              </select></div>
          </div>
        </Panel>

        <Panel title="Area of interest" pad={false}>
          <Tabs<Method> value={method} onChange={setMethod} tabs={[{ key: "demo", label: "Demo event" }, { key: "draw", label: "Draw polygon" }, { key: "coordinates", label: "Coordinates" }, { key: "admin", label: "Admin area" }, { key: "upload", label: "Upload GeoJSON" }]} />
          <div className="p-3">
            {method === "demo" && (
              <div className="grid gap-2 md:grid-cols-2">
                {sc?.scenarios.map((s: any) => (
                  <label key={s.key} className={`cursor-pointer rounded border p-2.5 ${scenario === s.key ? "border-accent bg-accent/10" : "border-line"}`}>
                    <input type="radio" className="mr-2" checked={scenario === s.key} onChange={() => setScenario(s.key)} />
                    <b className="text-xs text-strong">{s.title}</b>
                    <span className={`ml-2 rounded px-1.5 py-0.5 text-[11px] font-semibold ${s.mode === "live" ? "bg-ok/15 text-ok" : "bg-warn/15 text-warn"}`}>{s.mode === "live" ? "Real data" : "Simulated"}</span>
                    <div className="mt-1 text-xs text-muted">{s.description}</div>
                    {s.mode === "live" && <div className="mt-1 text-[11px] text-muted">Satellite window: before {s.pre_end}, after {s.post_start} to {s.post_end}. Retrieval takes 1-3 minutes the first time.</div>}
                  </label>
                ))}
              </div>
            )}
            {method === "draw" && (
              <div className="space-y-2">
                <AoiDrawMap points={pts} onChange={setPts} online={online} />
                <div className="flex items-center gap-2 text-xs text-muted">
                  <button type="button" className="btn btn-sm" onClick={() => setPts(pts.slice(0, -1))}>Undo</button>
                  <button type="button" className="btn btn-sm" onClick={() => setPts([])}>Clear</button>
                  <label className="flex items-center gap-1.5"><input type="checkbox" checked={online} onChange={(e) => setOnline(e.target.checked)} /> Online basemap (needs internet)</label>
                  <span>{pts.length} point(s). Click the map to add vertices (4-900 km²).</span>
                </div>
              </div>
            )}
            {method === "coordinates" && (
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                {(["west", "south", "east", "north"] as const).map((k) => (
                  <div key={k}><label className="label" htmlFor={k}>{k} ({k === "west" || k === "east" ? "lon" : "lat"})</label><input id={k} className="input tabular-nums" value={coords[k]} onChange={(e) => setCoords({ ...coords, [k]: e.target.value })} /></div>
                ))}
              </div>
            )}
            {method === "admin" && (
              <div><label className="label" htmlFor="adm">Administrative area</label>
                <select id="adm" className="input" value={admin} onChange={(e) => setAdmin(e.target.value)}>{sc?.admin_areas.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
                <p className="mt-1 text-xs text-muted">Bounding boxes are coarse placeholders for this demo, not official boundaries. Large districts exceed the 900 km² AOI limit and will be rejected.</p></div>
            )}
            {method === "upload" && (
              <div className="space-y-2">
                <input type="file" accept=".json,.geojson,application/geo+json,application/json" onChange={(e) => onFile(e.target.files?.[0])} className="text-xs" />
                <textarea className="input h-32 tabular-nums text-xs" value={geojson} onChange={(e) => setGeojson(e.target.value)} placeholder='{"type":"Polygon","coordinates":[[[lon,lat],...]]}' />
              </div>
            )}
          </div>
        </Panel>
        {method !== "demo" && (
          <Panel title="Data source">
            <div className="mb-2 flex gap-2">
              <button type="button" className={`btn ${dataMode === "live" ? "btn-primary" : ""}`} onClick={() => setDataMode("live")}>Real satellite data</button>
              <button type="button" className={`btn ${dataMode === "simulated" ? "btn-primary" : ""}`} onClick={() => setDataMode("simulated")}>Simulated (demonstration)</button>
            </div>
            {dataMode === "live" ? (
              <div className="space-y-2">
                <div className="grid grid-cols-3 gap-3">
                  {([["pre_end", "Last pre-event date"], ["post_start", "Post-event window start"], ["post_end", "Post-event window end"]] as const).map(([k, l]) => (
                    <div key={k}><label className="label" htmlFor={k}>{l}</label><input id={k} type="date" className="input" value={(dates as any)[k]} onChange={(e) => setDates({ ...dates, [k]: e.target.value })} /></div>
                  ))}
                </div>
                <p className="text-xs text-muted">Retrieves Sentinel-1 (same orbit track before/after), Sentinel-2, Copernicus DEM, ESA WorldCover, WorldPop population, OpenStreetMap roads/facilities and Open-Meteo rainfall. Area limit 400 km². Needs internet.</p>
              </div>
            ) : <p className="text-xs text-warn">Imagery, population, roads and facilities will be simulated and labelled DEMONSTRATION DATA.</p>}
          </Panel>
        )}
        <ErrorBox error={err} />
        <button className="btn btn-primary" disabled={busy}>{busy ? "Creating…" : "Create event"}</button>
      </form>
    </div>
  );
}
