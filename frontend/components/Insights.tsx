"use client";
import Link from "next/link";
import { useState } from "react";
import { useApi } from "@/lib/hooks";
import { LEVEL_COLOR, ago, hhmm, num } from "@/lib/format";
import { Empty, LevelBadge, Spinner } from "./ui";

function Tile({ label, value, sub, color }: { label: string; value: React.ReactNode; sub?: string; color?: string }) {
  return (
    <div className="min-w-0 px-5 py-4">
      <div className="truncate text-sm text-muted">{label}</div>
      <div className="mt-1 text-3xl font-semibold tabular-nums leading-none" style={{ color: color || "#0b1b33" }}>{value}</div>
      {sub && <div className="mt-1.5 truncate text-xs text-muted">{sub}</div>}
    </div>
  );
}

/** Five headline numbers. The rest are one click away. */
export function KpiStrip({ k }: { k: any }) {
  const [more, setMore] = useState(false);
  const cov = k.resource_coverage;
  const stale = (k.data_freshness || []).filter((f: any) => f.stale).length;
  return (
    <div className="panel">
      <div className="grid grid-cols-2 divide-x divide-line md:grid-cols-5">
        <Tile label="Critical areas (P1)" value={k.levels.P1} color={LEVEL_COLOR.P1} />
        <Tile label="High priority (P2)" value={k.levels.P2} color={LEVEL_COLOR.P2} />
        <Tile label="People at high risk" value={num(k.people_at_risk)} sub={`${num(k.people_exposed)} exposed`} />
        <Tile label="People cut off" value={num(k.people_isolated)} sub="by blocked roads" />
        <Tile label="Hospitals at risk" value={k.critical_infrastructure.hospitals_at_risk} sub={`${k.critical_infrastructure.at_risk} facilities at risk in total`} />
      </div>
      {more && (
        <div className="grid grid-cols-2 divide-x divide-line border-t border-line md:grid-cols-5">
          <Tile label="Roads affected" value={k.roads.blocked + k.roads.potentially_blocked} sub={`${k.roads.blocked} blocked`} />
          <Tile label="Rescue teams free" value={k.resources.available.rescue_team ?? 0} sub={`${k.resources.deployed.rescue_team ?? 0} deployed`} />
          <Tile label="P1 areas without a team" value={k.resources.unassigned_p1.length} sub={`of ${k.resources.p1_total}`} color={k.resources.unassigned_p1.length ? LEVEL_COLOR.P1 : "#1f9d6b"} />
          <Tile label="P1 coverage" value={cov?.p1_coverage_pct != null ? `${cov.p1_coverage_pct}%` : "–"} sub={cov ? `about ${cov.est_response_delay_min ?? "–"} min to arrive` : "not planned yet"} />
          <Tile label="Data freshness" value={stale ? `${stale} out of date` : "Up to date"} sub={`assessment v${k.assessment_version}`} color={stale ? "#a56a00" : "#1f9d6b"} />
        </div>
      )}
      <button className="w-full border-t border-line py-2 text-xs text-muted hover:text-strong" onClick={() => setMore((m) => !m)}>{more ? "Fewer figures" : "More figures"}</button>
    </div>
  );
}

export function SummaryText({ eventId, version }: { eventId: number; version: number }) {
  const { data, loading } = useApi<any>(`/api/events/${eventId}/summary`, { deps: [version] });
  if (loading && !data) return <Spinner />;
  return <p className="text-[15px] leading-relaxed text-text">{data?.text}</p>;
}

/** Next steps: three by default; each shows its reason in plain text (no accordion). */
export function RecommendedActions({ eventId, version, limit = 3 }: { eventId: number; version: number; limit?: number }) {
  const { data, loading } = useApi<any>(`/api/events/${eventId}/recommendations`, { deps: [version] });
  const [all, setAll] = useState(false);
  const list: any[] = data?.actions || [];
  const shown = all ? list : list.slice(0, limit);
  if (loading && !data) return <Spinner />;
  if (!list.length) return <Empty>No recommendations yet. Run the analysis first.</Empty>;
  return (
    <div>
      <ol className="divide-y divide-line">
        {shown.map((a) => (
          <li key={a.rank} className="py-3 first:pt-0">
            <div className="flex items-baseline gap-3">
              <span className="text-sm tabular-nums text-muted">{a.rank}</span>
              <div className="min-w-0">
                <div className="text-[15px] font-medium text-strong">{a.action}</div>
                <div className="mt-0.5 text-sm text-muted">{a.why.slice(0, 2).join(" · ")}</div>
              </div>
            </div>
          </li>
        ))}
      </ol>
      {list.length > limit && <button className="mt-1 text-sm text-accent hover:underline" onClick={() => setAll((a) => !a)}>{all ? "Show fewer" : `Show all ${list.length}`}</button>}
    </div>
  );
}

/** The five most urgent areas, one line each. */
export function TopAreas({ eventId, version }: { eventId: number; version: number }) {
  const { data, loading } = useApi<any>(`/api/events/${eventId}/priorities?level=P1&limit=5`, { deps: [version] });
  if (loading && !data) return <Spinner />;
  const cells: any[] = data?.cells || [];
  if (!cells.length) return <Empty>No critical areas right now.</Empty>;
  return (
    <ul className="divide-y divide-line">
      {cells.map((c) => (
        <li key={c.h3_index}>
          <Link href={`/events/${eventId}/priorities?cell=${c.cell_no}`} className="flex items-center gap-3 py-3 first:pt-0 hover:text-accent">
            <span className="w-14 shrink-0 text-[15px] font-medium text-strong">Cell {String(c.cell_no).padStart(2, "0")}</span>
            <LevelBadge level={c.level} small />
            <span className="min-w-0 flex-1 truncate text-sm text-muted">{c.reason_codes[0]}</span>
            <span className="text-sm tabular-nums text-muted">{num(c.population_exposed)} people</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

/** Shown only when there are at least two assessments to compare. */
export function WhatChanged({ eventId, version }: { eventId: number; version: number }) {
  const { data } = useApi<any>(version > 1 ? `/api/events/${eventId}/what-changed` : null, { deps: [version] });
  if (!data?.available) return null;
  return (
    <div>
      <div className="mb-2 text-sm text-muted">Compared with the previous assessment (v{data.from_version} → v{data.to_version})</div>
      <ul className="space-y-1 text-[15px] text-strong">{data.lines.map((l: string) => <li key={l}>{l}</li>)}</ul>
      {data.escalations.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {data.escalations.slice(0, 5).map((e: any) => (
            <div key={e.h3_index} className="flex items-center gap-2 text-sm">
              <LevelBadge level={e.from} small /><span className="text-muted">→</span><LevelBadge level={e.to} small /><b className="text-strong">Cell {String(e.cell_no).padStart(2, "0")}</b>
              <span className="truncate text-muted">{e.reasons.join(", ")}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function AlertList({ eventId, version, limit = 5 }: { eventId: number; version: number; limit?: number }) {
  const { data } = useApi<any>(`/api/events/${eventId}/alerts`, { deps: [version], poll: 10000 });
  const color = { critical: "#d62f35", warning: "#e0721a", info: "#1d6fd8" } as Record<string, string>;
  const list: any[] = data?.alerts?.slice(0, limit) || [];
  if (!list.length) return <div className="text-sm text-muted">No alerts.</div>;
  return (
    <ul className="divide-y divide-line">
      {list.map((a) => (
        <li key={a.id} className="flex gap-3 py-2.5 first:pt-0" >
          <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: color[a.severity] }} />
          <div className="min-w-0 flex-1"><div className="text-sm font-medium text-strong">{a.title}</div><div className="truncate text-xs text-muted">{a.detail}</div></div>
          <span className="shrink-0 text-xs tabular-nums text-muted">{hhmm(a.at)}</span>
        </li>
      ))}
    </ul>
  );
}

export function FreshnessList({ items }: { items: any[] }) {
  return (
    <div className="space-y-1.5">
      {items.map((f) => (
        <div key={f.key} className="flex items-center justify-between gap-4 text-sm">
          <span className="text-muted">{f.name}</span>
          <span className={f.stale ? "font-medium text-warn" : "text-text"}>{f.stale ? "Out of date · " : ""}{ago(f.last_updated)}{f.simulated ? " · simulated" : ""}</span>
        </div>
      ))}
    </div>
  );
}
