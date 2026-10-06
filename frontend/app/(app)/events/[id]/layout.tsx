"use client";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { HAZARD_LABEL } from "@/lib/format";
import EventScope from "@/components/EventScope";
import { useEvent } from "@/components/EventContext";
import { DemoBadge, ErrorBox, Menu, RealBadge } from "@/components/ui";

const MAIN_TABS = [["", "Overview"], ["map", "Map"], ["priorities", "Priorities"], ["resources", "Resources"], ["field", "Field"], ["reports", "Reports"]] as const;
const MORE_TABS = [["analysis", "Satellite analysis"], ["predictions", "Predictions"], ["routes", "Routes"], ["shelters", "Shelters"], ["timeline", "Timeline"]] as const;

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
  const moreActive = MORE_TABS.some(([seg]) => path === `${base}/${seg}`);
  const tab = (active: boolean) => `whitespace-nowrap border-b-2 px-3 py-2.5 text-sm ${active ? "border-accent font-medium text-strong" : "border-transparent text-muted hover:text-strong"}`;
  return (
    <div className={`flex flex-col ${isMap ? "h-full" : ""}`}>
      <div className="shrink-0 border-b border-line bg-panel px-6 pt-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <Link href="/events" className="text-sm text-muted hover:text-strong">‹ Events</Link>
            <h1 className="truncate text-lg font-semibold text-strong">{ev.name}</h1>
            <span className="rounded-full border border-line px-2.5 py-0.5 text-xs text-muted">{HAZARD_LABEL[ev.hazard] || ev.hazard}</span>
            {ev.is_demo ? <DemoBadge /> : <RealBadge />}
            {running && <span className="text-sm text-accent">Analysing…</span>}
          </div>
          <div className="flex items-center gap-2">
            {can("event.process") && <button className="btn btn-primary" disabled={busy} onClick={() => analyse(true)}>{running ? "Analysing…" : ev.assessment_version ? "Re-run analysis" : "Run analysis"}</button>}
            <Menu label="More">
              {(close) => (
                <>
                  {ev.assessment_version > 0 && <Link role="menuitem" className="block px-3 py-2 text-sm text-text hover:bg-panel2" href={`${base}/present`} onClick={close}>Presentation mode</Link>}
                  {can("event.process") && ev.is_demo && ev.assessment_version > 0 && <button role="menuitem" className="block w-full px-3 py-2 text-left text-sm text-text hover:bg-panel2" disabled={busy} onClick={() => { close(); newPass(true); }}>Simulate a new satellite pass</button>}
                  <Link role="menuitem" className="block px-3 py-2 text-sm text-text hover:bg-panel2" href="/events" onClick={close}>All events</Link>
                </>
              )}
            </Menu>
          </div>
        </div>
        <ErrorBox error={actionErr} />
        {running && <div className="mt-3 h-1 overflow-hidden rounded bg-ink"><div className="h-full bg-accent transition-all" style={{ width: `${Math.max(5, (status.job?.progress || 0) * 100)}%` }} /></div>}
        <nav className="mt-3 flex items-center gap-1 overflow-x-auto">
          {MAIN_TABS.map(([seg, label]) => {
            const href = seg ? `${base}/${seg}` : base;
            return <Link key={label} href={href} className={tab(path === href)}>{label}</Link>;
          })}
          <Menu label={<span className={moreActive ? "font-medium text-strong" : ""}>More</span>} align="left">
            {(close) => MORE_TABS.map(([seg, label]) => <Link key={seg} role="menuitem" href={`${base}/${seg}`} onClick={close} className={`block px-3 py-2 text-sm hover:bg-panel2 ${path === `${base}/${seg}` ? "font-medium text-strong" : "text-text"}`}>{label}</Link>)}
          </Menu>
        </nav>
      </div>
      <div className={isMap ? "min-h-0 flex-1 p-3" : "px-6 py-8"}>{isMap ? children : <div className="mx-auto max-w-6xl">{children}</div>}</div>
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
