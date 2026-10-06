"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useApi } from "@/lib/hooks";
import { dt } from "@/lib/format";
import { useEvent } from "@/components/EventContext";
import Pipeline from "@/components/Pipeline";
import { AlertFeed, FreshnessList, KpiStrip, RecommendedActions, SummaryPanel, WhatChanged } from "@/components/Insights";
import { ConfBadge, Empty, LevelBadge, Panel, Spinner } from "@/components/ui";

export default function Overview() {
  const { id } = useParams<{ id: string }>();
  const { event: ev, status, analyse, busy } = useEvent();
  const version = ev?.assessment_version ?? 0;
  const { data: k } = useApi<any>(`/api/events/${id}/kpis`, { deps: [version] });
  const { data: p1 } = useApi<any>(`/api/events/${id}/priorities?level=P1&limit=8`, { deps: [version] });
  const { data: health } = useApi<any>(`/api/events/${id}/data-health`, { deps: [version] });
  if (!ev || !status) return <Spinner />;

  return (
    <div className="space-y-4">
      {!version && (
        <div className="panel flex flex-wrap items-center justify-between gap-3 border-accent/50 p-4">
          <div><div className="text-sm font-bold text-strong">This event has not been analysed yet.</div><div className="text-xs text-muted">Run the pipeline to detect change, assess impact and generate priorities.</div></div>
          <button className="btn btn-primary" disabled={busy} onClick={() => analyse(true)}>{busy ? "Running…" : "Analyse event"}</button>
        </div>
      )}
      {k && version > 0 && <KpiStrip k={k} />}
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          {version > 0 && <SummaryPanel eventId={ev.id} version={version} />}
          {version > 0 && <RecommendedActions eventId={ev.id} version={version} />}
          {version > 0 && p1 && (
            <Panel title={`Top P1 locations (${p1.counts.P1})`} right={<Link className="text-[11px] text-accent" href={`/events/${id}/priorities`}>all priorities →</Link>} pad={false}>
              <table className="w-full"><tbody>
                {p1.cells.map((c: any) => (
                  <tr key={c.h3_index} className="border-b border-line/60 hover:bg-panel2">
                    <td className="td tabular-nums font-bold text-strong">CELL {String(c.cell_no).padStart(2, "0")}</td>
                    <td className="td"><LevelBadge level={c.level} small /> <span className="tabular-nums">{c.score.toFixed(2)}</span></td>
                    <td className="td"><ConfBadge value={c.confidence} label={c.confidence_label} /></td>
                    <td className="td text-muted">{c.reason_codes.slice(0, 3).join(" · ")}</td>
                  </tr>
                ))}
              </tbody></table>
            </Panel>
          )}
          {version > 0 && <WhatChanged eventId={ev.id} version={version} />}
        </div>
        <div className="space-y-4">
          <Panel title="Processing pipeline" right={<span className="text-[11px] text-muted">{status.job ? status.job.status : "not run"}</span>}>
            <Pipeline steps={status.steps} />
            {status.job?.error && <div className="mt-2 rounded border border-p1/50 bg-p1/10 p-2 text-xs text-p1">{status.job.error}</div>}
          </Panel>
          {version > 0 && <AlertFeed eventId={ev.id} version={version} />}
          <Panel title="Event details">
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
              <dt className="text-muted">Hazard</dt><dd className="text-right capitalize">{ev.hazard}</dd>
              <dt className="text-muted">Severity</dt><dd className="text-right ">{ev.severity}</dd>
              <dt className="text-muted">Start</dt><dd className="text-right">{dt(ev.start_date)}</dd>
              <dt className="text-muted">AOI</dt><dd className="text-right">{ev.aoi?.area_km2} km² ({ev.aoi?.method === "demo" ? "scenario" : ev.aoi?.method})</dd>
              <dt className="text-muted">H3 resolution</dt><dd className="text-right">{ev.h3_resolution}</dd>
              <dt className="text-muted">Last satellite pass</dt><dd className="text-right">{dt(ev.last_satellite_pass)}</dd>
              <dt className="text-muted">Last analysis</dt><dd className="text-right">{dt(ev.last_analysis)}</dd>
            </dl>
          </Panel>
          {health?.sensor_mode && (
            <Panel title="Sensor decision">
              <div className="mb-1 tabular-nums text-sm font-bold text-accent">{health.sensor_mode}</div>
              <p className="text-xs leading-snug text-muted">{health.sensor_explanation}</p>
            </Panel>
          )}
          {health && <Panel title="Data freshness"><FreshnessList items={health.freshness} />{health.stale_layers.length > 0 && <div className="mt-2 text-xs text-warn">Stale layers: {health.stale_layers.join(", ")}</div>}</Panel>}
        </div>
      </div>
      {version === 0 && <Empty>Results appear here after analysis.</Empty>}
    </div>
  );
}
