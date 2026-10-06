"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";

type Msg = { q: string; a?: any; err?: string };
const SUGGESTED = ["Which areas should we rescue first?", "How many people are currently at high risk?", "Which hospital is most at risk?", "What changed since the previous assessment?", "Which locations may escalate in the next 6 hours?", "What should I do next?", "How are shelters looking?"];

export default function CopilotPanel({ eventId, version, compact }: { eventId: number; version: number; compact?: boolean }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { setMsgs([]); }, [eventId]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  async function ask(text: string) {
    if (!text.trim() || busy) return;
    setQ(""); setBusy(true);
    setMsgs((m) => [...m, { q: text }]);
    try {
      const a = await api(`/api/events/${eventId}/copilot`, { body: { question: text } });
      setMsgs((m) => m.map((x, i) => (i === m.length - 1 ? { ...x, a } : x)));
    } catch (e: any) {
      setMsgs((m) => m.map((x, i) => (i === m.length - 1 ? { ...x, err: e.message } : x)));
    } finally { setBusy(false); }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        {!msgs.length && (
          <div>
            <p className="mb-2 text-xs text-muted">DISHA Copilot answers from the event&apos;s actual database values (priorities, routes, predictions, resources, data health). If the data is not there, it says so. It does not guess.</p>
            <div className="flex flex-wrap gap-1.5">{SUGGESTED.slice(0, compact ? 4 : 7).map((s) => <button key={s} className="rounded border border-line bg-panel2 px-2 py-1 text-left text-xs hover:border-accent" onClick={() => ask(s)}>{s}</button>)}</div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className="space-y-1.5">
            <div className="ml-6 rounded bg-accent/15 px-2.5 py-1.5 text-xs text-strong">{m.q}</div>
            {m.err && <div className="mr-6 rounded border border-p1/40 bg-p1/10 px-2.5 py-1.5 text-xs text-p1">{m.err}</div>}
            {m.a ? (
              <div className="mr-6 rounded border border-line bg-panel2 px-2.5 py-2 text-xs">
                <p className="leading-relaxed text-text">{m.a.answer}</p>
                <div className="mt-1.5 border-t border-line/60 pt-1 text-[11px] text-muted">
                  Intent: {m.a.intent} · Sources: {m.a.sources.join(", ") || "n/a"} · v{m.a.assessment_version} · {ago(m.a.generated_at)}<br />{m.a.provenance}
                </div>
              </div>
            ) : !m.err && <div className="mr-6 text-xs text-muted">Retrieving…</div>}
          </div>
        ))}
        <div ref={end} />
      </div>
      <form className="flex gap-2 border-t border-line p-2" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
        <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about this event… e.g. Why is cell 7 P1?" aria-label="Ask DISHA Copilot" disabled={!version} />
        <button className="btn btn-primary" disabled={busy || !q.trim() || !version}>Ask</button>
      </form>
    </div>
  );
}
