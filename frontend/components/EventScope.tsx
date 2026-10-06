"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { EventCtx, EventStatus } from "./EventContext";
import { ErrorBox, Spinner } from "./ui";

/** Provides event + live pipeline status to descendants and exposes analyse / new-pass actions. */
export default function EventScope({ id, children, onError }: { id: string | number; children: React.ReactNode; onError?: (e: string | null) => void }) {
  const [polling, setPolling] = useState(3000);
  const { data: status, error, reload } = useApi<EventStatus>(`/api/events/${id}/status`, { poll: polling });
  const [busy, setBusy] = useState(false);
  const running = !!status?.job && ["queued", "running"].includes(status.job.status);
  useEffect(() => { setPolling(running ? 700 : 5000); }, [running]);

  const act = useCallback(async (path: string) => {
    setBusy(true); onError?.(null);
    try { await api(path, { method: "POST" }); reload(); } catch (e: any) { onError?.(e.message); } finally { setBusy(false); }
  }, [reload, onError]);
  const analyse = useCallback((pace = false) => act(`/api/events/${id}/process${pace ? "?pace=true" : ""}`), [act, id]);
  const newPass = useCallback((pace = false) => act(`/api/events/${id}/new-pass${pace ? "?pace=true" : ""}`), [act, id]);

  if (error && !status) return <div className="p-4"><ErrorBox error={error} /></div>;
  if (!status) return <Spinner text="Loading event…" />;
  return <EventCtx.Provider value={{ event: status.event, status, refresh: reload, analyse, newPass, busy: busy || running }}>{children}</EventCtx.Provider>;
}
