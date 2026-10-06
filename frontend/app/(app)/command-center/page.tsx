"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { HAZARD_LABEL, ago, hhmm } from "@/lib/format";
import EventScope from "@/components/EventScope";
import { useEvent } from "@/components/EventContext";
import MapWorkspace from "@/components/MapWorkspace";
import Pipeline from "@/components/Pipeline";
import CopilotPanel from "@/components/CopilotPanel";
import DemoRunner from "@/components/DemoRunner";
import { AlertFeed, FreshnessList, KpiStrip, RecommendedActions } from "@/components/Insights";
import { DemoBadge, Empty, Panel, Spinner } from "@/components/ui";

function Live({ id }: { id: number }) {
  const { event: ev, status, analyse, busy } = useEvent();
  const version = ev?.assessment_version ?? 0;
  const { data: k } = useApi<any>(`/api/events/${id}/kpis`, { deps: [version] });
  const { data: tl } = useApi<any[]>(`/api/events/${id}/timeline`, { deps: [version], poll: 6000 });
  if (!ev || !status) return <Spinner />;
  return (
    <div className="space-y-3">
      {!version && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded border border-p1/60 bg-p1/10 p-3">
          <div><div className="text-[11px] font-bold   text-p1">{HAZARD_LABEL[ev.hazard]} alert detected</div><div className="text-sm font-bold text-strong">{ev.name}</div></div>
          <button className="btn btn-primary" disabled={busy} onClick={() => analyse(true)}>{busy ? "Analysing…" : "Analyse event"}</button>
        </div>
      )}
      {k && version > 0 && <KpiStrip k={k} />}
      <div className="grid gap-3 xl:grid-cols-[1fr_24rem]">
        <div className="h-[34rem]">{version > 0 ? <MapWorkspace eventId={id} /> : <Empty>The live map appears once analysis completes.</Empty>}</div>
        <div className="space-y-3">
          <Panel title="Pipeline"><Pipeline steps={status.steps} /></Panel>
          {version > 0 && <AlertFeed eventId={id} version={version} limit={5} />}
        </div>
      </div>
      {version > 0 && (
        <div className="grid gap-3 lg:grid-cols-3">
          <RecommendedActions eventId={id} version={version} limit={5} />
          <Panel title="Incident timeline" pad={false}>
            <ol className="max-h-72 overflow-y-auto p-3">{tl?.slice(-9).reverse().map((t) => <li key={t.id} className="flex gap-2 pb-1.5 text-xs"><span className="w-16 shrink-0 whitespace-nowrap tabular-nums text-muted">{hhmm(t.at)}</span><span className="text-text">{t.title}</span></li>)}</ol>
          </Panel>
          <Panel title="Ask DISHA Copilot" pad={false}><div className="h-72"><CopilotPanel eventId={id} version={version} compact /></div></Panel>
        </div>
      )}
      {k && <Panel title="Data freshness"><FreshnessList items={k.data_freshness} /></Panel>}
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
    <div className="p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded border border-accent/40 bg-accent/10 px-3 py-2 text-xs">
        <span><b className="text-strong">Naye hain?</b> Pehle 2-minute guide padhein ki DISHA kya hai aur kaise use karein.</span>
        <Link href="/guide" className="btn btn-primary btn-sm">Guide kholein →</Link>
      </div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-bold  text-strong">Command Centre</h1>
          <div className="text-xs text-muted">{cc ? `${cc.totals.active_events} active event(s) · ${cc.totals.p1} P1 · ${cc.totals.p2} P2 · ${cc.totals.people_at_risk.toLocaleString()} people at risk` : "Loading…"}</div>
        </div>
        <div className="flex items-center gap-2">
          {cc?.events.length > 0 && (
            <select className="input w-72" value={id ?? ""} onChange={(e) => setId(+e.target.value)} aria-label="Active event">
              {cc.events.map((r: any) => <option key={r.event.id} value={r.event.id}>{r.event.code} · {r.event.name}{r.event.assessment_version ? "" : " (not analysed)"}</option>)}
            </select>
          )}
          {can("event.write") && <button className="btn btn-primary" onClick={() => setDemo(true)}>▶ Run DISHA demo</button>}
          {id && <Link className="btn" href={`/events/${id}/present`}>Presentation mode</Link>}
        </div>
      </div>
      {loading && !cc ? <Spinner /> : !cc?.events.length ? (
        <div className="panel mx-auto mt-10 max-w-xl p-8 text-center">
          <div className="tabular-nums text-3xl font-bold  text-strong">DISHA</div>
          <p className="mt-2 text-sm text-muted">No events yet. Start the guided demonstration to see the complete loop: detect → predict → prioritise → plan → dispatch → verify → recalculate.</p>
          <div className="mt-4 flex justify-center gap-2">{can("event.write") && <button className="btn btn-primary" onClick={() => setDemo(true)}>▶ Run DISHA demo</button>}<Link className="btn" href="/events">Browse scenarios</Link></div>
          <div className="mt-3"><DemoBadge /></div>
        </div>
      ) : id ? <EventScope key={id} id={id}><Live id={id} /></EventScope> : null}
      {demo && <DemoRunner existingEventId={id} onEvent={(n) => { setId(n); reload(); }} onClose={() => { setDemo(false); reload(); }} />}
    </div>
  );
}
