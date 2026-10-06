"use client";
import { useParams } from "next/navigation";
import { useApi } from "@/lib/hooks";
import { authedUrl } from "@/lib/api";
import { dt, fixed, pct } from "@/lib/format";
import { useEvent } from "@/components/EventContext";
import { DemoBadge, Empty, Panel, RealBadge, Spinner } from "@/components/ui";

export default function Analysis() {
  const { id } = useParams<{ id: string }>();
  const { event } = useEvent();
  const version = event?.assessment_version ?? 0;
  const { data, loading } = useApi<any>(`/api/events/${id}/detections`, { deps: [version] });
  const { data: ev } = useApi<any>(`/api/events/${id}/evaluation`, { deps: [version] });
  const { data: models } = useApi<any[]>(`/api/models`);
  const { data: health } = useApi<any>(`/api/events/${id}/data-health`, { deps: [version] });
  if (!version) return <Empty>Run analysis to see satellite intelligence and detection results.</Empty>;
  if (loading && !data) return <Spinner />;
  const d = data?.detections[0];
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
        {[["sar_pre", `Pre-event radar (VV)${event?.is_demo ? ", simulated" : ""}`], ["sar_post", `Post-event radar (VV)${event?.is_demo ? ", simulated" : ""}`], ["hazard", `${(event?.hazard || "").charAt(0).toUpperCase() + (event?.hazard || "").slice(1)} detection (severity)`],
          ...(event && !event.is_demo ? [["optical", "Sentinel-2 true colour (post-event)"]] : [])].map(([k, label]) => (
          <Panel key={k} title={label} right={event?.is_demo ? <DemoBadge /> : <RealBadge />}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={authedUrl(`/api/events/${id}/layers/${k}.png`)} alt={label} className="aspect-square w-full rounded border border-line object-cover [image-rendering:pixelated]" />
          </Panel>
        ))}
      </div>
      {d && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Detection result">
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
              <dt className="text-muted">Model</dt><dd className="text-right tabular-nums">{d.model_name} v{d.model_version}</dd>
              <dt className="text-muted">Sensor mode</dt><dd className="text-right tabular-nums text-accent">{d.sensor_mode}</dd>
              <dt className="text-muted">Detected area</dt><dd className="text-right tabular-nums">{fixed(d.area_km2, 2)} km²</dd>
              <dt className="text-muted">Mean confidence</dt><dd className="text-right tabular-nums">{pct(d.mean_confidence)}</dd>
              <dt className="text-muted">Mean severity</dt><dd className="text-right tabular-nums">{pct(d.mean_severity)}</dd>
              <dt className="text-muted">Input data</dt><dd className={`text-right ${d.simulated_input ? "text-warn" : "text-ok"}`}>{d.simulated_input ? "Simulated" : "Real (open data)"}</dd>
              <dt className="text-muted">Computed</dt><dd className="text-right">{dt(d.created_at)}</dd>
            </dl>
            <p className="mt-3 rounded border border-line bg-panel2 p-2 text-xs text-muted">{d.sensor_explanation}</p>
            <h4 className="label mt-3">Hazard outputs</h4>
            <pre className="max-h-48 overflow-auto rounded bg-ink p-2 tabular-nums text-[11px] text-muted">{JSON.stringify(Object.fromEntries(Object.entries(d.outputs).filter(([k]) => k !== "hotspot_locations")), null, 1)}</pre>
          </Panel>
          <Panel title="Method & thresholds">
            <pre className="max-h-72 overflow-auto rounded bg-ink p-2 tabular-nums text-[11px] leading-relaxed text-muted">{JSON.stringify(d.stats, null, 1)}</pre>
          </Panel>
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Satellite passes">
          <table className="w-full"><thead><tr><th className="th">Sensor</th><th className="th">Phase</th><th className="th">Acquired</th><th className="th">Cloud</th><th className="th">Source</th></tr></thead>
            <tbody>{data?.passes.map((p: any, i: number) => <tr key={i} className="border-t border-line/60"><td className="td">{p.sensor}</td><td className="td capitalize">{p.phase}</td><td className="td">{dt(p.acquired_at)}</td><td className="td tabular-nums">{p.cloud_cover_pct != null ? `${Math.round(p.cloud_cover_pct)}%` : "-"}</td><td className={`td text-[11px] ${p.simulated ? "text-warn" : "text-muted"}`}>{p.source}</td></tr>)}</tbody></table>
        </Panel>
        <Panel title="Change-detection engine - pluggable detectors">
          <ul className="space-y-1.5 text-xs">
            {data?.detectors.map((x: any) => (
              <li key={x.key} className="rounded border border-line p-2">
                <div className="flex items-center justify-between"><b className="text-strong">{x.name}</b><span className={`text-[11px] font-bold ${x.available ? "text-ok" : "text-muted"}`}>{x.available ? "AVAILABLE" : "UNAVAILABLE"}</span></div>
                <div className="text-[11px]  text-muted">{x.kind} · v{x.version}</div>
                {!x.available && <div className="text-xs text-muted">{x.detail}</div>}
              </li>
            ))}
          </ul>
        </Panel>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Data health">
          {health && (
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
              <dt className="text-muted">Satellite availability</dt><dd className="text-right tabular-nums">{health.satellite_availability_pct}%</dd>
              <dt className="text-muted">Cloud quality</dt><dd className="text-right tabular-nums">{health.cloud_quality_pct}% (cloud {health.cloud_cover_pct != null ? Math.round(health.cloud_cover_pct) : "-"}%)</dd>
              <dt className="text-muted">Population data</dt><dd className="text-right">{health.population}</dd>
              <dt className="text-muted">Road data</dt><dd className="text-right">{health.roads}</dd>
              <dt className="text-muted">Weather data</dt><dd className="text-right">{health.weather}</dd>
              <dt className="text-muted">Field observations</dt><dd className="text-right tabular-nums">{health.field_observations}</dd>
            </dl>
          )}
        </Panel>
        <Panel title="Model evaluation">
          {ev?.available ? (
            <table className="w-full text-xs"><tbody>{["accuracy", "precision", "recall", "f1", "iou", "false_positive_rate"].map((k) => <tr key={k} className="border-b border-line/60"><td className="td capitalize text-muted">{k.replace(/_/g, " ")}</td><td className="td text-right tabular-nums">{ev[k] ?? "-"}</td></tr>)}</tbody></table>
          ) : <div className="rounded border border-warn/40 bg-warn/10 p-3 text-xs text-warn">{ev?.message}</div>}
          <p className="mt-2 text-[11px] text-muted">Metrics are only shown when real ground truth has been registered for an event. No accuracy values are invented.</p>
        </Panel>
      </div>
      <Panel title="Model registry" pad={false}>
        <table className="w-full"><thead><tr className="border-b border-line"><th className="th">Model</th><th className="th">Hazard</th><th className="th">Kind</th><th className="th">Status</th><th className="th">Training data</th><th className="th">Accuracy</th></tr></thead>
          <tbody>{models?.map((m) => <tr key={m.id} className="border-b border-line/60"><td className="td tabular-nums">{m.name} v{m.version}</td><td className="td">{m.hazard}</td><td className="td capitalize">{m.kind}</td><td className="td capitalize">{m.status.replace("_", " ")}</td><td className="td text-muted">{m.training_dataset}</td><td className="td tabular-nums">{m.accuracy ?? "unknown"}</td></tr>)}</tbody></table>
      </Panel>
    </div>
  );
}
