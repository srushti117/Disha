"use client";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { ago, HAZARD_LABEL } from "@/lib/format";
import EventScope from "@/components/EventScope";
import { useEvent } from "@/components/EventContext";
import { DemoBadge, ErrorBox, RealBadge } from "@/components/ui";

const TABS = [
  ["", "Overview"], ["map", "Map"], ["analysis", "Analysis"], ["priorities", "Priorities"], ["predictions", "Predictions"], ["resources", "Resources"],
  ["routes", "Routes"], ["shelters", "Shelters"], ["field", "Field"], ["reports", "Reports"], ["timeline", "Timeline"],
] as const;

function Header({ children, actionErr }: { children: React.ReactNode; actionErr: string | null }) {
  const { id } = useParams<{ id: string }>();
  const path = usePathname();
  const { can } = useAuth();
  const { event: ev, status, analyse, newPass, busy } = useEvent();
  useEffect(() => { try { window.localStorage.setItem("disha_event", String(id)); } catch {} }, [id]);
  if (!ev || !status) return null;
  const running = !!status.job && ["queued", "running"].includes(status.job.status);
  const base = `/events/${id}`;
  const isMap = path === `${base}/map`;
  return (
    <div className={`flex flex-col ${isMap ? "h-full" : ""}`}>
      <div className="shrink-0 border-b border-line bg-panel px-4 pt-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-3">
            <Link href="/events" className="text-xs text-muted hover:text-strong">‹ Events</Link>
            <span className="tabular-nums text-xs text-muted">{ev.code}</span>
            <h1 className="truncate text-sm font-bold text-strong">{ev.name}</h1>
            <span className="rounded border border-line px-1.5 py-0.5 text-[11px] font-bold   text-text">{HAZARD_LABEL[ev.hazard] || ev.hazard}</span>
            <span className={`rounded px-1.5 py-0.5 text-[11px] font-bold  ${running ? "bg-accent/20 text-accent" : ev.status === "active" ? "bg-ok/20 text-ok" : ev.status === "failed" ? "bg-p1/20 text-p1" : "bg-muted/20 text-muted"}`}>{running ? "processing" : ev.status}</span>
            {ev.is_demo ? <DemoBadge /> : <RealBadge />}
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden text-[11px] text-muted lg:inline">v{ev.assessment_version} · analysed {ago(ev.last_analysis)} · last pass {ago(ev.last_satellite_pass)}</span>
            {can("event.process") && <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => analyse(true)}>{running ? "Analysing…" : ev.assessment_version ? "Re-analyse" : "Analyse event"}</button>}
            {can("event.process") && ev.is_demo && ev.assessment_version > 0 && <button className="btn btn-sm" disabled={busy} onClick={() => newPass(true)} title="Simulate a later satellite pass; the hazard has progressed">New satellite pass</button>}
            {ev.assessment_version > 0 && <Link className="btn btn-sm" href={`${base}/present`}>Presentation</Link>}
          </div>
        </div>
        <ErrorBox error={actionErr} />
        {running && <div className="mt-2 h-1 overflow-hidden rounded bg-ink"><div className="h-full bg-accent transition-all" style={{ width: `${Math.max(5, (status.job?.progress || 0) * 100)}%` }} /></div>}
        <nav className="mt-2 flex gap-0.5 overflow-x-auto">
          {TABS.map(([seg, label]) => {
            const href = seg ? `${base}/${seg}` : base;
            return <Link key={label} href={href} className={`whitespace-nowrap px-3 py-1.5 text-xs font-semibold   ${path === href ? "border-b-2 border-accent text-strong" : "text-muted hover:text-text"}`}>{label}</Link>;
          })}
        </nav>
      </div>
      <div className={isMap ? "min-h-0 flex-1 p-2" : "p-4"}>{children}</div>
    </div>
  );
}

export default function EventLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const [err, setErr] = useState<string | null>(null);
  const path = usePathname();
  if (path?.endsWith("/present")) return <EventScope id={id}>{children}</EventScope>;
  return <EventScope id={id} onError={setErr}><Header actionErr={err}>{children}</Header></EventScope>;
}
