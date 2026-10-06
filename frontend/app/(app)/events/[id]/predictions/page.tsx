"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useApi } from "@/lib/hooks";
import { pct } from "@/lib/format";
import { useEvent } from "@/components/EventContext";
import { LevelBars } from "@/components/Charts";
import { ConfBadge, Empty, EstimateBadge, LevelBadge, PageHeader, Panel, Spinner } from "@/components/ui";

export default function Predictions() {
  const { id } = useParams<{ id: string }>();
  const { event } = useEvent();
  const version = event?.assessment_version ?? 0;
  const { data, loading } = useApi<any>(`/api/events/${id}/predictions`, { deps: [version] });
  const [h, setH] = useState(6);
  if (!version) return <Empty>Run analysis to generate risk predictions.</Empty>;
  if (loading && !data) return <Spinner />;
  const cur = data.current;
  const sel = data.horizons.find((x: any) => x.horizon_h === h) || data.horizons[0];
  const labels = ["Current", ...data.horizons.map((x: any) => `+${x.horizon_h} h`)];
  return (
    <div className="space-y-4">
      <PageHeader title={<span className="flex items-center gap-2">Risk prediction <EstimateBadge /></span>} sub={data.label} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Current vs predicted">
          <div className="grid grid-cols-2 gap-3">
            <div><div className="label">Current</div><div className="tabular-nums text-3xl font-bold text-p1">P1: {cur.P1}</div></div>
            <div><div className="label">Predicted +{sel.horizon_h} h</div><div className="tabular-nums text-3xl font-bold text-p1">P1: {sel.counts.P1}</div></div>
          </div>
          <div className="mt-3 rounded border border-accent/40 bg-accent/10 p-2 text-xs"><b className="text-strong">{sel.p1_new}</b> location(s) estimated to escalate to P1 · <b className="text-strong">{sel.escalating_count}</b> to a higher level</div>
          <div className="mt-2 flex gap-1">{data.horizons.map((x: any) => <button key={x.horizon_h} className={`btn btn-sm ${x.horizon_h === h ? "btn-primary" : ""}`} onClick={() => setH(x.horizon_h)}>+{x.horizon_h}h</button>)}</div>
        </Panel>
        <Panel title="Priority distribution over time" className="lg:col-span-2">
          <div className="h-52"><LevelBars labels={labels} series={["P1", "P2", "P3", "P4"].map((l) => ({ level: l, values: [cur[l], ...data.horizons.map((x: any) => x.counts[l])] }))} /></div>
        </Panel>
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
        <Panel title={`Locations likely to escalate within ${sel.horizon_h} h`} pad={false} right={<Link href={`/events/${id}/map`} className="text-[11px] text-accent">open time machine →</Link>}>
          <table className="w-full"><thead><tr className="border-b border-line"><th className="th">Cell</th><th className="th">Now</th><th className="th">Predicted</th><th className="th">Probability</th><th className="th">Confidence</th><th className="th">Drivers</th></tr></thead>
            <tbody>
              {sel.escalations.map((e: any) => (
                <tr key={e.h3_index} className="border-b border-line/60">
                  <td className="td tabular-nums font-bold text-strong">{String(e.cell_no).padStart(2, "0")}</td><td className="td"><LevelBadge level={e.current} small /></td><td className="td"><LevelBadge level={e.predicted} small /></td>
                  <td className="td tabular-nums">{pct(e.probability)}</td><td className="td"><ConfBadge label={e.confidence_label.replace(" CONFIDENCE", "")} /></td><td className="td text-xs text-muted">{e.drivers.join(" · ")}</td>
                </tr>
              ))}
            </tbody></table>
          {!sel.escalations.length && <div className="p-4 text-xs text-muted">No escalations estimated at this horizon.</div>}
        </Panel>
        <Panel title="Model & inputs">
          <dl className="space-y-1.5 text-xs">
            <div className="flex justify-between"><dt className="text-muted">Model</dt><dd className="tabular-nums">{data.model?.name} v{data.model?.version}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Rainfall (mm)</dt><dd className="tabular-nums">{Object.entries(data.weather?.rainfall_mm || {}).map(([k, v]) => `${k}h:${v}`).join(" ")}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">River trend</dt><dd className="tabular-nums">{data.weather?.river_level_trend_m_per_h} m/h</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Wind</dt><dd className="tabular-nums">{data.weather?.wind_kmh} km/h</dd></div>
          </dl>
          <p className="mt-2 text-[11px] text-warn">{data.weather?.source}. {data.weather?.note}</p>
          <p className="mt-2 text-[11px] text-muted">Hand-set logistic coefficients over neighbour hazard state, terrain, rainfall and river trend. Not trained or validated on observed progression; confidence decays with horizon.</p>
        </Panel>
      </div>
    </div>
  );
}
