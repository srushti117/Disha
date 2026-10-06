"use client";
import { useParams } from "next/navigation";
import { useApi } from "@/lib/hooks";
import { authedUrl } from "@/lib/api";
import { dt, fixed, pct } from "@/lib/format";
import { useEvent } from "@/components/EventContext";
import { Disclosure, Empty, PageHeader, Panel, Spinner } from "@/components/ui";

function Img({ id, k, label }: { id: string; k: string; label: string }) {
  return (
    <div>
      <div className="mb-2 text-sm font-medium text-strong">{label}</div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={authedUrl(`/api/events/${id}/layers/${k}.png`)} alt={label} className="aspect-square w-full rounded-md border border-line object-cover [image-rendering:pixelated]" />
    </div>
  );
}

export default function Analysis() {
  const { id } = useParams<{ id: string }>();
  const { event } = useEvent();
  const version = event?.assessment_version ?? 0;
  const { data, loading } = useApi<any>(`/api/events/${id}/detections`, { deps: [version] });
  const { data: ev } = useApi<any>(`/api/events/${id}/evaluation`, { deps: [version] });
  const { data: models } = useApi<any[]>(`/api/models`);
  const { data: health } = useApi<any>(`/api/events/${id}/data-health`, { deps: [version] });
  if (!version) return <Empty>Run the analysis to see the satellite results.</Empty>;
  if (loading && !data) return <Spinner />;
  const d = data?.detections[0];
  const real = event && !event.is_demo;
  const hazard = (event?.hazard || "").charAt(0).toUpperCase() + (event?.hazard || "").slice(1);
  return (
    <div className="space-y-6">
      <PageHeader title="Satellite analysis" sub={real ? "Real Sentinel imagery and open map data" : "Simulated demonstration imagery"} />

      <Panel>
        <div className="grid gap-6 md:grid-cols-2">
          <Img id={id} k={real ? "optical" : "sar_post"} label={real ? "Satellite image after the event" : "Radar image after the event (simulated)"} />
          <Img id={id} k="hazard" label={`${hazard} detected`} />
        </div>
      </Panel>

      {d && (
        <Panel title="What was detected">
          <dl className="grid grid-cols-[12rem_1fr] gap-y-2 text-sm">
            <dt className="text-muted">Affected area</dt><dd className="font-medium tabular-nums text-strong">{fixed(d.area_km2, 1)} km²</dd>
            <dt className="text-muted">Confidence</dt><dd className="tabular-nums">{pct(d.mean_confidence)} average</dd>
            <dt className="text-muted">Method</dt><dd>{d.model_name} v{d.model_version}</dd>
            <dt className="text-muted">Satellite source used</dt><dd>{d.sensor_mode}</dd>
            <dt className="text-muted">Input data</dt><dd className={d.simulated_input ? "text-warn" : "text-ok"}>{d.simulated_input ? "Simulated" : "Real (open data)"}</dd>
          </dl>
          <p className="mt-4 rounded-md bg-panel2 p-3 text-sm text-muted">{d.sensor_explanation}</p>
        </Panel>
      )}

      <div className="space-y-3">
        <Disclosure title="Radar before and after">
          <div className="grid gap-6 md:grid-cols-2"><Img id={id} k="sar_pre" label="Radar before the event" /><Img id={id} k="sar_post" label="Radar after the event" /></div>
        </Disclosure>
        <Disclosure title="Satellite passes used">
          <table className="w-full text-sm"><thead><tr><th className="th">Sensor</th><th className="th">Phase</th><th className="th">Acquired</th><th className="th">Cloud</th><th className="th">Source</th></tr></thead>
            <tbody>{data?.passes.map((p: any, i: number) => <tr key={i} className="border-t border-line/60"><td className="td">{p.sensor}</td><td className="td capitalize">{p.phase}</td><td className="td">{dt(p.acquired_at)}</td><td className="td tabular-nums">{p.cloud_cover_pct != null ? `${Math.round(p.cloud_cover_pct)}%` : "–"}</td><td className={`td text-xs ${p.simulated ? "text-warn" : "text-muted"}`}>{p.source}</td></tr>)}</tbody></table>
        </Disclosure>
        <Disclosure title="Data quality and accuracy">
          <div className="grid gap-6 md:grid-cols-2">
            {health && (
              <dl className="grid grid-cols-[10rem_1fr] gap-y-1.5 text-sm">
                <dt className="text-muted">Satellite availability</dt><dd>{health.satellite_availability_pct}%</dd>
                <dt className="text-muted">Cloud-free</dt><dd>{health.cloud_quality_pct != null ? `${health.cloud_quality_pct}%` : "–"}</dd>
                <dt className="text-muted">Population data</dt><dd>{health.population}</dd>
                <dt className="text-muted">Road data</dt><dd>{health.roads}</dd>
                <dt className="text-muted">Weather data</dt><dd>{health.weather}</dd>
                <dt className="text-muted">Field observations</dt><dd>{health.field_observations}</dd>
              </dl>
            )}
            <div className="text-sm text-muted">
              {ev?.available ? "Accuracy figures come from registered ground truth." : ev?.message}
              <p className="mt-2 text-xs">No accuracy numbers are shown unless real ground truth has been registered for this event.</p>
            </div>
          </div>
        </Disclosure>
        <Disclosure title="Technical details">
          <div className="space-y-5">
            <div><div className="mb-1 text-sm font-medium text-strong">Thresholds and masks</div><pre className="max-h-64 overflow-auto rounded-md bg-panel2 p-3 text-xs text-muted">{JSON.stringify(d?.stats, null, 1)}</pre></div>
            <div><div className="mb-1 text-sm font-medium text-strong">Detection engines</div>
              <ul className="space-y-1 text-sm">{data?.detectors.map((x: any) => <li key={x.key} className="flex justify-between gap-3"><span>{x.name} <span className="text-muted">v{x.version}</span></span><span className={x.available ? "text-ok" : "text-muted"}>{x.available ? "available" : "not available"}</span></li>)}</ul></div>
            <div><div className="mb-1 text-sm font-medium text-strong">Model registry</div>
              <table className="w-full text-sm"><tbody>{models?.map((m) => <tr key={m.id} className="border-t border-line/60"><td className="td">{m.name} v{m.version}</td><td className="td text-muted">{m.hazard}</td><td className="td capitalize text-muted">{m.status.replace("_", " ")}</td></tr>)}</tbody></table></div>
          </div>
        </Disclosure>
      </div>
    </div>
  );
}
