"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { LEVEL_COLOR, ago, hhmm, num } from "@/lib/format";
import { Empty, LevelBadge, Panel, Spinner } from "./ui";

export function KpiStrip({ k, big }: { k: any; big?: boolean }) {
  const cell = (label: string, value: any, sub?: string, color?: string) => (
    <div className="min-w-0 border-r border-line px-3 py-2 last:border-r-0">
      <div className="truncate text-[11px] font-semibold   text-muted">{label}</div>
      <div className={`tabular-nums font-bold leading-tight ${big ? "text-3xl" : "text-2xl"}`} style={{ color: color || "#0b1b33" }}>{value}</div>
      {sub && <div className="truncate text-[11px] text-muted">{sub}</div>}
    </div>
  );
  const cov = k.resource_coverage;
  const stale = (k.data_freshness || []).filter((f: any) => f.stale).length;
  return (
    <div className="panel grid grid-cols-2 md:grid-cols-5 xl:grid-cols-10">
      {cell("P1 locations", k.levels.P1, "Critical", LEVEL_COLOR.P1)}
      {cell("P2 locations", k.levels.P2, "High", LEVEL_COLOR.P2)}
      {cell("People at risk", num(k.people_at_risk), `${num(k.people_exposed)} exposed`)}
      {cell("Isolated", num(k.people_isolated), "potentially cut off")}
      {cell("Critical infra", `${k.critical_infrastructure.at_risk}/${k.critical_infrastructure.total}`, `${k.critical_infrastructure.hospitals_at_risk} hospital(s) at risk`)}
      {cell("Roads affected", k.roads.blocked + k.roads.potentially_blocked, `${k.roads.blocked} blocked`)}
      {cell("Rescue teams", k.resources.available.rescue_team ?? 0, `${k.resources.deployed.rescue_team ?? 0} deployed`)}
      {cell("Unassigned P1", k.resources.unassigned_p1.length, `of ${k.resources.p1_total}`, k.resources.unassigned_p1.length ? LEVEL_COLOR.P1 : "#35c28a")}
      {cell("P1 coverage", cov?.p1_coverage_pct != null ? `${cov.p1_coverage_pct}%` : "-", cov ? `delay ~${cov.est_response_delay_min ?? "-"} min` : "run optimise")}
      {cell("Data freshness", stale ? `${stale} stale` : "OK", `v${k.assessment_version}`, stale ? "#f2c744" : "#35c28a")}
    </div>
  );
}

export function SummaryPanel({ eventId, version }: { eventId: number; version: number }) {
  const { data, loading } = useApi<any>(`/api/events/${eventId}/summary`, { deps: [version] });
  return (
    <Panel title="Situation summary" right={<span className="text-[11px] text-muted">generated from database values</span>}>
      {loading && !data ? <Spinner /> : <p className="text-sm leading-relaxed text-text">{data?.text}</p>}
      {data?.disclaimer && <p className="mt-2 text-[11px] text-warn">{data.disclaimer}</p>}
    </Panel>
  );
}

export function RecommendedActions({ eventId, version, limit = 8 }: { eventId: number; version: number; limit?: number }) {
  const { data, loading } = useApi<any>(`/api/events/${eventId}/recommendations`, { deps: [version] });
  const [open, setOpen] = useState<number | null>(1);
  return (
    <Panel title="What should I do?" right={<span className="text-[11px] text-muted">recommendations cite system data</span>}>
      {loading && !data ? <Spinner /> : !data?.actions.length ? <Empty>No recommendations yet - run analysis.</Empty> : (
        <ol className="space-y-1">
          {data.actions.slice(0, limit).map((a: any) => (
            <li key={a.rank} className="rounded border border-line bg-panel2">
              <button className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left" onClick={() => setOpen(open === a.rank ? null : a.rank)}>
                <span className="tabular-nums text-xs text-accent">{a.rank}.</span>
                <span className="flex-1 text-xs font-semibold text-strong">{a.action}</span>
                <span className="text-[11px] text-muted">{open === a.rank ? "−" : "WHY"}</span>
              </button>
              {open === a.rank && (
                <div className="border-t border-line px-2.5 py-1.5 text-xs text-muted">
                  <b className="text-text">Why:</b> {a.why.join(" · ")}
                  {a.cell_no && <Link className="ml-2 text-accent hover:underline" href={`/events/${eventId}/priorities?cell=${a.cell_no}`}>Cell {String(a.cell_no).padStart(2, "0")} →</Link>}
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}

export function WhatChanged({ eventId, version }: { eventId: number; version: number }) {
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    try { setRes(await api(`/api/events/${eventId}/what-changed`)); } finally { setBusy(false); }
  }
  return (
    <Panel title="What changed?" right={<button className="btn btn-sm btn-primary" onClick={go} disabled={busy}>{busy ? "Comparing…" : "What changed?"}</button>}>
      {!res ? <div className="text-xs text-muted">Compare the current assessment (v{version}) with the previous one.</div> : !res.available ? <div className="text-xs text-muted">{res.message}</div> : (
        <div>
          <div className="mb-2 text-xs text-muted">v{res.from_version} → v{res.to_version}</div>
          <ul className="space-y-0.5 tabular-nums text-sm text-strong">{res.lines.map((l: string) => <li key={l}>{l}</li>)}</ul>
          {res.pct.affected_area != null && <div className="mt-2 text-xs text-muted">Affected area {res.pct.affected_area > 0 ? "+" : ""}{res.pct.affected_area}% · population at risk {res.pct.population_at_risk != null ? `${res.pct.population_at_risk > 0 ? "+" : ""}${res.pct.population_at_risk}%` : "n/a"}</div>}
          {res.escalations.length > 0 && (
            <div className="mt-2 space-y-1">
              {res.escalations.slice(0, 6).map((e: any) => (
                <div key={e.h3_index} className="flex items-center gap-2 text-xs">
                  <LevelBadge level={e.from} small /><span>→</span><LevelBadge level={e.to} small /><b className="text-strong">Cell {String(e.cell_no).padStart(2, "0")}</b><span className="truncate text-muted">{e.reasons.join(", ")}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

export function AlertFeed({ eventId, version, limit = 8 }: { eventId: number; version: number; limit?: number }) {
  const { data } = useApi<any>(`/api/events/${eventId}/alerts`, { deps: [version], poll: 8000 });
  const color = { critical: "#e5484d", warning: "#f08a24", info: "#3b9eff" } as Record<string, string>;
  return (
    <Panel title="Alerts" right={<Link href={`/events/${eventId}/timeline`} className="text-[11px] text-accent">all →</Link>} pad={false}>
      <ul className="max-h-72 divide-y divide-line/60 overflow-y-auto">
        {!data?.alerts.length && <li className="p-3 text-xs text-muted">No alerts.</li>}
        {data?.alerts.slice(0, limit).map((a: any) => (
          <li key={a.id} className="flex gap-2 px-3 py-1.5" style={{ borderLeft: `3px solid ${color[a.severity]}` }}>
            <div className="min-w-0 flex-1"><div className="truncate text-xs font-semibold text-strong">{a.title}</div><div className="truncate text-[11px] text-muted">{a.detail}</div></div>
            <span className="shrink-0 tabular-nums text-[11px] text-muted">{hhmm(a.at)}</span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function FreshnessList({ items }: { items: any[] }) {
  return (
    <div className="space-y-1">
      {items.map((f) => (
        <div key={f.key} className="flex items-center justify-between text-xs">
          <span className="text-muted">{f.name}</span>
          <span className={f.stale ? "font-semibold text-warn" : "text-text"}>{f.stale ? "⚠ STALE " : ""}{ago(f.last_updated)}{f.simulated ? " · sim" : ""}</span>
        </div>
      ))}
    </div>
  );
}
