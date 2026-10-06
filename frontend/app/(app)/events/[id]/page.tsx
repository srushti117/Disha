"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useApi } from "@/lib/hooks";
import { dt } from "@/lib/format";
import { useEvent } from "@/components/EventContext";
import Pipeline from "@/components/Pipeline";
import { AlertList, FreshnessList, KpiStrip, RecommendedActions, SummaryText, TopAreas, WhatChanged } from "@/components/Insights";
import { Disclosure, Panel, Spinner } from "@/components/ui";

export default function Overview() {
  const { id } = useParams<{ id: string }>();
  const { event: ev, status, analyse, busy } = useEvent();
  const version = ev?.assessment_version ?? 0;
  const { data: k } = useApi<any>(`/api/events/${id}/kpis`, { deps: [version] });
  const { data: health } = useApi<any>(`/api/events/${id}/data-health`, { deps: [version] });
  const { data: alerts } = useApi<any>(version ? `/api/events/${id}/alerts` : null, { deps: [version] });
  if (!ev || !status) return <Spinner />;
  const running = !!status.job && ["queued", "running"].includes(status.job.status);
  const nAlerts = alerts?.alerts?.length ?? 0;

  if (!version) {
    return (
      <div className="space-y-6">
        <Panel>
          <div className="flex flex-wrap items-center justify-between gap-6">
            <div>
              <div className="text-lg font-semibold text-strong">This event has not been analysed yet</div>
              <div className="mt-1 text-sm text-muted">Run the analysis to detect the affected area and rank where to respond first.</div>
            </div>
            <button className="btn btn-primary" disabled={busy} onClick={() => analyse(true)}>{busy ? "Running…" : "Run analysis"}</button>
          </div>
        </Panel>
        {(running || status.job) && <Panel title="Progress"><Pipeline steps={status.steps} />{status.job?.error && <div className="mt-3 rounded border border-p1/50 bg-p1/10 p-3 text-sm text-p1">{status.job.error}</div>}</Panel>}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {k && <KpiStrip k={k} />}

      <Panel title="Situation summary"><SummaryText eventId={ev.id} version={version} /></Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Recommended next steps" right={<Link href={`/events/${id}/resources`} className="text-sm text-accent hover:underline">Plan resources</Link>}>
          <RecommendedActions eventId={ev.id} version={version} />
        </Panel>
        <Panel title="Most urgent areas" right={<Link href={`/events/${id}/priorities`} className="text-sm text-accent hover:underline">All priorities</Link>}>
          <TopAreas eventId={ev.id} version={version} />
        </Panel>
      </div>

      <div className="space-y-3">
        {version > 1 && <Disclosure title="What changed since the last assessment"><WhatChanged eventId={ev.id} version={version} /></Disclosure>}
        <Disclosure title="Alerts" hint={nAlerts ? `${nAlerts}` : "none"}><AlertList eventId={ev.id} version={version} /></Disclosure>
        <Disclosure title="Data sources and method" hint={health?.sensor_mode}>
          <div className="space-y-5">
            {health?.sensor_mode && (
              <div>
                <div className="text-sm font-medium text-strong">How the satellite data was used ({health.sensor_mode})</div>
                <p className="mt-1 text-sm text-muted">{health.sensor_explanation}</p>
              </div>
            )}
            {health && (
              <div>
                <div className="mb-1.5 text-sm font-medium text-strong">Data freshness</div>
                <FreshnessList items={health.freshness} />
              </div>
            )}
            <div>
              <div className="mb-1.5 text-sm font-medium text-strong">Event details</div>
              <dl className="grid grid-cols-[10rem_1fr] gap-y-1.5 text-sm">
                <dt className="text-muted">Hazard</dt><dd className="capitalize">{ev.hazard}</dd>
                <dt className="text-muted">Area</dt><dd>{ev.aoi?.area_km2} km²</dd>
                <dt className="text-muted">Last satellite pass</dt><dd>{dt(ev.last_satellite_pass)}</dd>
                <dt className="text-muted">Last analysis</dt><dd>{dt(ev.last_analysis)}</dd>
                <dt className="text-muted">Assessment version</dt><dd>v{ev.assessment_version}</dd>
              </dl>
            </div>
          </div>
        </Disclosure>
        <Disclosure title="Analysis steps" hint={running ? "running" : "complete"}><Pipeline steps={status.steps} /></Disclosure>
      </div>
    </div>
  );
}
