"use client";
import { useEffect, useState } from "react";
import { useApi } from "@/lib/hooks";
import CopilotPanel from "@/components/CopilotPanel";
import { Empty, PageHeader, Panel } from "@/components/ui";

export default function CopilotPage() {
  const { data: events } = useApi<any[]>("/api/events");
  const [id, setId] = useState<number | null>(null);
  useEffect(() => {
    if (!events?.length || id) return;
    let saved: number | null = null;
    try { saved = Number(window.localStorage.getItem("disha_event")) || null; } catch {}
    setId(events.find((e) => e.id === saved)?.id ?? events.find((e) => e.assessment_version)?.id ?? events[0].id);
  }, [events, id]);
  const ev = events?.find((e) => e.id === id);
  return (
    <div className="mx-auto flex h-full max-w-4xl flex-col p-4">
      <PageHeader title="DISHA Copilot" sub="Grounded Q&A over live event data - explains, retrieves and summarises; it does not decide"
        right={<select className="input w-72" value={id ?? ""} onChange={(e) => setId(+e.target.value)} aria-label="Event">{events?.map((e) => <option key={e.id} value={e.id}>{e.code} · {e.name}</option>)}</select>} />
      {!events?.length ? <Empty>Create an event first.</Empty> : id && (
        <Panel className="min-h-0 flex-1" pad={false}><div className="h-[calc(100vh-14rem)]"><CopilotPanel eventId={id} version={ev?.assessment_version ?? 0} /></div></Panel>
      )}
      {ev && !ev.assessment_version && <div className="mt-2 text-xs text-warn">This event has not been analysed - the Copilot needs analysis results to answer.</div>}
    </div>
  );
}
