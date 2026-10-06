"use client";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { api, authedUrl } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { LEVEL_COLOR, ago, num, pct } from "@/lib/format";
import { useEvent } from "@/components/EventContext";
import { Empty, ErrorBox, LevelBadge, PageHeader, Panel, Spinner } from "@/components/ui";

const VERDICTS = [["confirmed", "Confirmed"], ["false_alarm", "False alarm"], ["partially_affected", "Partially affected"], ["severe", "Severe"], ["resolved", "Resolved"]] as const;

function Inner() {
  const { id } = useParams<{ id: string }>();
  const sp = useSearchParams();
  const { can, user } = useAuth();
  const { event, refresh } = useEvent();
  const version = event?.assessment_version ?? 0;
  const { data: missions, reload } = useApi<any[]>(`/api/events/${id}/missions`, { deps: [version] });
  const { data: reports, reload: reloadReports } = useApi<any[]>(`/api/events/${id}/field-reports`, { deps: [version] });
  const [sel, setSel] = useState<number | null>(null);
  const [verdict, setVerdict] = useState<string>("confirmed");
  const [notes, setNotes] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const [nav, setNav] = useState<any>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!missions?.length || sel !== null) return;
    const c = sp.get("cell");
    const m = (c && missions.find((x) => x.h3_index === c)) || missions[0];
    setSel(m.id);
  }, [missions, sp, sel]);
  const mission = useMemo(() => missions?.find((m) => m.id === sel) || null, [missions, sel]);
  if (!version) return <Empty>Run analysis first - missions are generated from P1/P2 cells.</Empty>;
  if (!missions) return <Spinner />;
  const canReport = can("field.report");

  const run = async (name: string, fn: () => Promise<any>) => { setBusy(name); setErr(null); try { return await fn(); } catch (e: any) { setErr(e.message); } finally { setBusy(null); } };
  const setStatus = (status: string) => run("status", async () => { await api(`/api/events/${id}/missions/${mission.id}/status`, { body: { status } }); reload(); });
  const navigate = () => run("nav", async () => setNav(await api(`/api/events/${id}/routes`, { body: { h3_index: mission.h3_index } })));
  async function submit(forceVerdict?: string) {
    const v = forceVerdict || verdict;
    await run("report", async () => {
      const f = new FormData();
      f.append("h3_index", mission.h3_index); f.append("verdict", v); f.append("notes", notes); f.append("mission_id", String(mission.id));
      files.forEach((x) => f.append("photos", x));
      const r = await api(`/api/events/${id}/field-reports`, { form: f });
      setResult(r); setNotes(""); setFiles([]); if (fileRef.current) fileRef.current.value = "";
      reload(); reloadReports(); refresh();
    });
  }
  async function simulate(v: string, kind: string) {
    await run("sim", async () => {
      const r = await api(`/api/events/${id}/field-reports/simulate`, { body: { h3_index: mission.h3_index, verdict: v, kind } });
      setResult(r); reload(); reloadReports(); refresh();
    });
  }

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Field mode" sub={`Signed in as ${user?.name} (${user?.role})`} />
      <ErrorBox error={err} />
      <div className="grid gap-4 md:grid-cols-[18rem_1fr]">
        <div className="space-y-2">
          <div className="label">Missions ({missions.length})</div>
          {missions.length === 0 && <Empty>No missions.</Empty>}
          {missions.map((m) => (
            <button key={m.id} onClick={() => { setSel(m.id); setResult(null); setNav(null); }} className={`w-full rounded border p-2.5 text-left ${sel === m.id ? "border-accent bg-accent/10" : "border-line bg-panel hover:border-muted"}`} style={{ borderLeft: `4px solid ${LEVEL_COLOR[m.priority] || "#6b7a90"}` }}>
              <div className="flex items-center justify-between"><b className="tabular-nums text-sm text-strong">{m.label}</b><LevelBadge level={m.priority} small /></div>
              <div className="text-xs text-muted">Cell {String(m.cell_no).padStart(2, "0")} · {m.kind} · <span className="">{m.status}</span>{m.field_status !== "unverified" && ` · ${m.field_status}`}</div>
            </button>
          ))}
        </div>

        {mission ? (
          <div className="space-y-4">
            <Panel>
              <div className="tabular-nums text-2xl font-bold  text-strong">{mission.label}</div>
              <dl className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
                <div><dt className="label">Cell</dt><dd className="tabular-nums text-lg text-strong">{String(mission.cell_no).padStart(2, "0")}</dd></div>
                <div><dt className="label">Priority</dt><dd><LevelBadge level={mission.priority} /></dd></div>
                <div><dt className="label">Mission</dt><dd className="text-sm font-bold text-strong">{mission.kind}</dd></div>
                <div><dt className="label">Population</dt><dd className="tabular-nums text-lg text-strong">{num(mission.population)}</dd></div>
                <div><dt className="label">Risk</dt><dd className="font-bold" style={{ color: mission.risk === "HIGH" ? LEVEL_COLOR.P1 : LEVEL_COLOR.P3 }}>{mission.risk}</dd></div>
                <div className="col-span-3"><dt className="label">Brief</dt><dd className="text-xs text-text">{mission.brief} - {mission.recommended_action}</dd></div>
              </dl>
              {canReport && (
                <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-5">
                  <button className="btn btn-primary" disabled={busy === "status" || mission.status !== "pending"} onClick={() => setStatus("accepted")}>Accept mission</button>
                  <button className="btn" disabled={busy === "nav"} onClick={navigate}>Navigate</button>
                  <button className="btn" onClick={() => document.getElementById("report-form")?.scrollIntoView({ behavior: "smooth" })}>Report status</button>
                  <button className="btn" onClick={() => fileRef.current?.click()}>Upload photo</button>
                  <button className="btn btn-danger" disabled={busy === "report"} onClick={() => submit("resolved")}>Mark resolved</button>
                </div>
              )}
              {nav && (
                <div className="mt-3 rounded border border-line bg-panel2 p-2.5 text-xs">
                  {nav.routes.filter((r: any) => r.recommended).map((r: any) => <div key={r.kind}><b className="text-ok">Recommended: {r.label}</b> · {r.distance_km} km · ETA {Math.round(r.eta_min)} min · risk {pct(r.risk)}</div>)}
                  {!nav.recommended && <b className="text-p1">No fully open road route - boat/air access required.</b>}
                  {nav.last_mile_note && <div className="text-warn">{nav.last_mile_note}</div>}
                  <a className="mt-1 inline-block text-accent underline" target="_blank" rel="noreferrer" href={`https://www.google.com/maps/dir/?api=1&destination=${mission.lat},${mission.lon}`}>Open destination in external maps (online)</a>
                </div>
              )}
            </Panel>

            {canReport && (
              <Panel title="Report status" className="scroll-mt-4">
                <div id="report-form" className="space-y-3">
                  <div className="flex flex-wrap gap-1.5">
                    {VERDICTS.map(([k, l]) => <button key={k} onClick={() => setVerdict(k)} className={`btn ${verdict === k ? "btn-primary" : ""}`}>{l}</button>)}
                  </div>
                  <textarea className="input h-20" placeholder="Observations (what you see on the ground)…" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000} />
                  <div>
                    <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" multiple onChange={(e) => setFiles(Array.from(e.target.files || []))} className="text-xs" />
                    {files.length > 0 && <div className="mt-1 text-xs text-muted">{files.length} photo(s) selected</div>}
                  </div>
                  <button className="btn btn-primary" disabled={busy === "report"} onClick={() => submit()}>{busy === "report" ? "Submitting…" : "Submit report"}</button>
                </div>
              </Panel>
            )}
            {canReport && user && ["commander", "admin"].includes(user.role) && (
              <Panel title="Demo: simulate a field report" right={<span className="text-[11px] font-bold text-warn">SIMULATED</span>}>
                <p className="mb-2 text-xs text-muted">Generates a clearly synthetic placeholder image and verdict for this cell, then recalculates priority (used by the presentation flow).</p>
                <div className="flex flex-wrap gap-1.5">
                  <button className="btn btn-sm" disabled={busy === "sim"} onClick={() => simulate("severe", "flood")}>Severe · flood water</button>
                  <button className="btn btn-sm" disabled={busy === "sim"} onClick={() => simulate("confirmed", "mud")}>Confirmed · debris</button>
                  <button className="btn btn-sm" disabled={busy === "sim"} onClick={() => simulate("false_alarm", "flood")}>False alarm</button>
                  <button className="btn btn-sm" disabled={busy === "sim"} onClick={() => simulate("resolved", "flood")}>Resolved</button>
                </div>
              </Panel>
            )}

            {result && (
              <Panel title="FIELD VERIFIED" right={result.label ? <span className="text-[11px] font-bold text-warn">SIMULATED</span> : undefined}>
                <div className="flex flex-wrap items-center gap-3 text-sm">
                  <span>Cell {String(result.cell_no).padStart(2, "0")}</span><LevelBadge level={result.before.level} /><span>→</span><LevelBadge level={result.after.level} />
                  <span className="tabular-nums text-xs text-muted">PI {result.before.score.toFixed(2)} → {result.after.score.toFixed(2)} · confidence {pct(result.before.confidence)} → {pct(result.after.confidence)}</span>
                </div>
                <p className="mt-1 text-xs text-muted">{result.effect_note}</p>
                {result.photo_analysis?.map((a: any, i: number) => (
                  <div key={i} className="mt-2 rounded border border-line bg-panel2 p-2 text-xs">
                    <b className="text-strong">Photo analysis</b> (heuristic): Detected: {a.detected.length ? a.detected.join(", ") : "nothing notable"} · estimated severity {a.estimated_severity} · confidence {pct(a.confidence)}
                    <div className="text-[11px] text-muted">{a.disclaimer}</div>
                  </div>
                ))}
                {result.escalations?.length > 0 && <div className="mt-2 text-xs text-warn">{result.escalations.slice(0, 3).map((e: any) => e.message).join(" · ")}</div>}
              </Panel>
            )}
          </div>
        ) : <Empty>Select a mission.</Empty>}
      </div>

      <Panel title={`Field observations (${reports?.length ?? 0})`} className="mt-4" pad={false}>
        <table className="w-full"><thead><tr className="border-b border-line"><th className="th">When</th><th className="th">Cell</th><th className="th">Verdict</th><th className="th">Effect</th><th className="th">Photos</th></tr></thead>
          <tbody>{reports?.map((r) => (
            <tr key={r.id} className="border-b border-line/60"><td className="td text-muted">{ago(r.at)}{r.simulated && <span className="ml-1 text-[11px] font-bold text-warn">SIM</span>}</td>
              <td className="td tabular-nums">{String(r.cell_no).padStart(2, "0")}</td><td className="td capitalize">{r.verdict.replace("_", " ")}</td>
              <td className="td text-xs text-muted">{r.effect?.before ? `${r.effect.before.level} → ${r.effect.after.level}` : ""}</td>
              <td className="td">{r.photos.map((p: any) => (/* eslint-disable-next-line @next/next/no-img-element */ <img key={p.id} src={authedUrl(`/api/events/${id}/field-photos/${p.id}`)} alt="field" className="mr-1 inline h-9 w-12 rounded border border-line object-cover" />))}</td></tr>
          ))}</tbody></table>
        {!reports?.length && <div className="p-4 text-xs text-muted">No field reports yet.</div>}
      </Panel>
    </div>
  );
}

export default function Field() { return <Suspense fallback={<Spinner />}><Inner /></Suspense>; }
