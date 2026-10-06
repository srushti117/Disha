"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { HAZARD_LABEL } from "@/lib/format";
import EventScope from "@/components/EventScope";
import { useEvent } from "@/components/EventContext";
import MapWorkspace from "@/components/MapWorkspace";
import Pipeline from "@/components/Pipeline";
import DemoRunner from "@/components/DemoRunner";
import { AlertList, KpiStrip, RecommendedActions } from "@/components/Insights";
import { Empty, Panel, Spinner } from "@/components/ui";

function Live({ id }: { id: number }) {
  const { event: ev, status, analyse, busy } = useEvent();
  const version = ev?.assessment_version ?? 0;
  const { data: k } = useApi<any>(`/api/events/${id}/kpis`, { deps: [version] });
  if (!ev || !status) return <Spinner />;
  const running = !!status.job && ["queued", "running"].includes(status.job.status);
  return (
    <div className="space-y-6">
      {!version && (
        <Panel>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="text-sm text-muted">{HAZARD_LABEL[ev.hazard]} event</div>
              <div className="text-lg font-semibold text-strong">{ev.name}</div>
            </div>
            <button className="btn btn-primary" disabled={busy} onClick={() => analyse(true)}>{busy ? "Analysing…" : "Run analysis"}</button>
          </div>
        </Panel>
      )}
      {k && version > 0 && <KpiStrip k={k} />}
      <div className="grid gap-6 xl:grid-cols-[1fr_24rem]">
        <div className="h-[38rem]">{version > 0 ? <MapWorkspace eventId={id} /> : <Empty>The map appears once the analysis has finished.</Empty>}</div>
        <div className="space-y-6">
          {(running || !version) && <Panel title="Progress"><Pipeline steps={status.steps} /></Panel>}
          {version > 0 && (
            <>
              <Panel title="Next steps" right={<Link href={`/events/${id}`} className="text-sm text-accent hover:underline">Overview</Link>}><RecommendedActions eventId={id} version={version} limit={3} /></Panel>
              <Panel title="Recent alerts" right={<Link href={`/events/${id}/timeline`} className="text-sm text-accent hover:underline">Timeline</Link>}><AlertList eventId={id} version={version} limit={3} /></Panel>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function CommandCenter() {
  const { can } = useAuth();
  const { data: cc, loading, reload } = useApi<any>("/api/command-center", { poll: 10000 });
  const [id, setId] = useState<number | null>(null);
  const [demo, setDemo] = useState(false);

  useEffect(() => {
    if (!cc || id) return;
    let saved: number | null = null;
    try { saved = Number(window.localStorage.getItem("disha_event")) || null; } catch {}
    const evs = cc.events.map((r: any) => r.event);
    const pick = evs.find((e: any) => e.id === saved) || evs.find((e: any) => e.assessment_version) || evs[0];
    if (pick) setId(pick.id);
  }, [cc, id]);
  useEffect(() => { if (id) try { window.localStorage.setItem("disha_event", String(id)); } catch {} }, [id]);

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-strong">Command Centre</h1>
          <div className="mt-1 text-sm text-muted">
            {cc ? `${cc.totals.active_events} active event${cc.totals.active_events === 1 ? "" : "s"}` : "Loading…"} · New to DISHA? <Link href="/guide" className="text-accent hover:underline">Read the guide</Link>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {cc?.events.length > 0 && (
            <select className="input w-72" value={id ?? ""} onChange={(e) => setId(+e.target.value)} aria-label="Active event">
              {cc.events.map((r: any) => <option key={r.event.id} value={r.event.id}>{r.event.name}{r.event.assessment_version ? "" : " (not analysed)"}</option>)}
            </select>
          )}
          {can("event.write") && <button className="btn" onClick={() => setDemo(true)}>Run guided demo</button>}
        </div>
      </div>
      {loading && !cc ? <Spinner /> : !cc?.events.length ? (
        <Panel>
          <div className="mx-auto max-w-lg py-8 text-center">
            <div className="text-xl font-semibold text-strong">No events yet</div>
            <p className="mt-2 text-sm text-muted">Start from a real or simulated scenario, or run the guided demo to see the whole workflow in about a minute.</p>
            <div className="mt-5 flex justify-center gap-3">{can("event.write") && <button className="btn btn-primary" onClick={() => setDemo(true)}>Run guided demo</button>}<Link className="btn" href="/events">Browse scenarios</Link></div>
          </div>
        </Panel>
      ) : id ? <EventScope key={id} id={id}><Live id={id} /></EventScope> : null}
      {demo && <DemoRunner existingEventId={id} onEvent={(n) => { setId(n); reload(); }} onClose={() => { setDemo(false); reload(); }} />}
    </div>
  );
}
