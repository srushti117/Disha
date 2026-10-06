"use client";
import Link from "next/link";
import { useApi } from "@/lib/hooks";
import { HAZARD_LABEL, LEVEL_COLOR, ago, num } from "@/lib/format";
import { LevelBars } from "@/components/Charts";
import { DemoBadge, Empty, PageHeader, Panel, Spinner } from "@/components/ui";

export default function Dashboard() {
  const { data, loading } = useApi<any>("/api/command-center", { poll: 15000 });
  if (loading && !data) return <Spinner />;
  const rows = (data?.events || []).filter((r: any) => r.kpis);
  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <PageHeader title="Dashboard" sub="All active events at a glance" />
      {!data?.events.length ? <Empty>No events yet. <Link href="/events" className="text-accent underline">Create one</Link>.</Empty> : (
        <div className="space-y-6">
          {rows.length > 0 && (
            <Panel title="P-level distribution by event">
              <div className="h-56"><LevelBars labels={rows.map((r: any) => r.event.code)} series={["P1", "P2", "P3", "P4"].map((l) => ({ level: l, values: rows.map((r: any) => r.kpis.levels[l]) }))} /></div>
            </Panel>
          )}
          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
            {data.events.map((r: any) => {
              const e = r.event, k = r.kpis;
              return (
                <Link key={e.id} href={`/events/${e.id}`} className="panel block p-3 hover:border-accent">
                  <div className="flex items-start justify-between gap-2"><div><div className="tabular-nums text-[11px] text-muted">{e.code} · {HAZARD_LABEL[e.hazard]}</div><div className="text-sm font-bold text-strong">{e.name}</div></div>{e.is_demo && <DemoBadge />}</div>
                  {k ? (
                    <div className="mt-3 grid grid-cols-4 gap-2 text-center">
                      {(["P1", "P2", "P3", "P4"] as const).map((l) => <div key={l}><div className="tabular-nums text-xl font-bold" style={{ color: LEVEL_COLOR[l] }}>{k.levels[l]}</div><div className="text-[11px] text-muted">{l}</div></div>)}
                      <div className="col-span-2 text-left"><div className="label">People at risk</div><div className="tabular-nums text-sm text-strong">{num(k.people_at_risk)}</div></div>
                      <div className="col-span-2 text-left"><div className="label">Hospitals at risk</div><div className="tabular-nums text-sm text-strong">{k.critical_infrastructure.hospitals_at_risk}</div></div>
                    </div>
                  ) : <div className="mt-3 text-xs text-warn">Not analysed yet</div>}
                  <div className="mt-2 text-[11px] text-muted">{e.status.toUpperCase()} · analysed {ago(e.last_analysis)}</div>
                </Link>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
