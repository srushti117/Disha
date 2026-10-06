"use client";
import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { LEVEL_COLOR } from "@/lib/format";
import Pipeline, { Step } from "./Pipeline";
import { LevelBadge } from "./ui";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
type Line = { t: string; tone?: "info" | "ok" | "warn" };

/** RUN DISHA DEMO: alert -> acquire -> detect -> assess -> prioritise -> predict -> route -> allocate -> field verify -> recalc (~45-60 s). */
export default function DemoRunner({ onEvent, onClose, existingEventId }: { onEvent: (id: number) => void; onClose: () => void; existingEventId?: number | null }) {
  const [lines, setLines] = useState<Line[]>([]);
  const [steps, setSteps] = useState<Step[]>([]);
  const [state, setState] = useState<"idle" | "running" | "done" | "error">("idle");
  const [eid, setEid] = useState<number | null>(null);
  const [final, setFinal] = useState<any>(null);
  const say = (t: string, tone: Line["tone"] = "info") => setLines((l) => [...l, { t, tone }]);

  async function run() {
    setState("running"); setLines([]); setFinal(null);
    try {
      say("ALERT: Flood alert detected - Kerala (DEMONSTRATION DATA).", "warn");
      await sleep(1800);
      let id: number;
      const ev = await api("/api/events", { body: { hazard: "flood", aoi_method: "demo", scenario_key: "kerala_flood_2018" } });
      id = ev.id; setEid(id); onEvent(id);
      say(`Event ${ev.code} created from the Kerala Flood Demo scenario. AOI ${ev.aoi.area_km2} km².`);
      await sleep(1500);
      say("Acquiring pre/post-event Sentinel-1 SAR + Sentinel-2 (SIMULATED passes)…");
      await api(`/api/events/${id}/process?pace=true`, { method: "POST" });
      let st: any;
      for (let i = 0; i < 200; i++) {
        await sleep(600);
        st = await api(`/api/events/${id}/status`);
        setSteps(st.steps);
        if (st.job && ["succeeded", "failed"].includes(st.job.status)) break;
      }
      if (st.job.status !== "succeeded") throw new Error(st.job.error || "Analysis failed");
      const det = (await api(`/api/events/${id}/detections`)).detections[0];
      say(`${det.sensor_explanation}`);
      say(`DETECT: ${det.area_km2.toFixed(1)} km² flooded · mean confidence ${(det.mean_confidence * 100).toFixed(0)}% · model ${det.model_name} v${det.model_version}.`, "ok");
      await sleep(1800);
      const pr = await api(`/api/events/${id}/priorities?level=P1,P2,P3,P4&limit=1`);
      say(`PRIORITISE: P1 = ${pr.counts.P1} · P2 = ${pr.counts.P2} · P3 = ${pr.counts.P3} · P4 = ${pr.counts.P4}.`, "ok");
      const p1 = (await api(`/api/events/${id}/priorities?level=P1&limit=1`)).cells[0];
      const cell = await api(`/api/events/${id}/cells/${p1.h3_index}`);
      say(`WHY P1? Cell ${String(cell.cell_no).padStart(2, "0")}: ${cell.why.top_factors.slice(0, 3).join("; ")}. Confidence ${(cell.confidence.overall * 100).toFixed(0)}%.`);
      await sleep(3000);
      const pred = await api(`/api/events/${id}/predictions`);
      const h6 = pred.horizons.find((h: any) => h.horizon_h === 6);
      say(`PREDICT (estimate): P1 ${pred.current.P1} → ${h6.counts.P1} within 6 h; ${h6.p1_new} location(s) likely to escalate to P1.`, "warn");
      await sleep(3000);
      const rt = await api(`/api/events/${id}/routes`, { body: { h3_index: p1.h3_index } });
      say(`PLAN: ${rt.summary.split("\n").join(" | ")}`);
      await sleep(3000);
      const al = await api(`/api/events/${id}/resources/optimise`, { body: { commit: true } });
      const mine = al.assignments.filter((a: any) => a.h3_index === p1.h3_index).map((a: any) => a.resource);
      say(`DISPATCH: ${al.metrics.units_assigned} units allocated · P1 coverage ${al.metrics.p1_coverage_pct}% · Cell ${String(cell.cell_no).padStart(2, "0")} → ${mine.join(", ") || "none available"}.`, "ok");
      await api(`/api/events/${id}/resources/dispatch`, { body: { reason: "Demo dispatch" } });
      await sleep(3000);
      const p2 = (await api(`/api/events/${id}/priorities?level=P2&limit=1`)).cells[0];
      const target = p2 || p1;
      say(`VERIFY: responder uploads a SIMULATED field report for Cell ${String(target.cell_no).padStart(2, "0")} (severe flooding).`);
      const fr = await api(`/api/events/${id}/field-reports/simulate`, { body: { h3_index: target.h3_index, verdict: "severe", kind: "flood" } });
      say(`FIELD VERIFIED: Cell ${String(fr.cell_no).padStart(2, "0")} ${fr.before.level} → ${fr.after.level} (PI ${fr.before.score.toFixed(2)} → ${fr.after.score.toFixed(2)}).`, "ok");
      if (fr.photo_analysis?.[0]) say(`Photo analysis (heuristic): ${fr.photo_analysis[0].detected.join(", ") || "nothing notable"} · severity ${fr.photo_analysis[0].estimated_severity} · confidence ${(fr.photo_analysis[0].confidence * 100).toFixed(0)}%.`);
      await sleep(2500);
      const k = await api(`/api/events/${id}/kpis`);
      say(`RECALCULATED: P1 = ${k.levels.P1} · P2 = ${k.levels.P2} · ${k.people_at_risk.toLocaleString()} people at high risk. Situation report is ready.`, "ok");
      setFinal({ fr, k });
      setState("done");
    } catch (e: any) {
      say(`Demo stopped: ${e.message}`, "warn");
      setState("error");
    }
  }

  const color = { info: "text-text", ok: "text-ok", warn: "text-warn" };
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4">
      <div className="panel flex max-h-[90vh] w-full max-w-3xl flex-col">
        <header className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <div><div className="text-[11px] font-bold   text-warn">DEMONSTRATION · SIMULATED DATA</div><h2 className="text-sm font-bold   text-strong">Run DISHA demo</h2></div>
          <button className="text-muted hover:text-strong" onClick={onClose} aria-label="Close">✕</button>
        </header>
        <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto p-4 md:grid-cols-[14rem_1fr]">
          <div><div className="label">Pipeline</div>{steps.length ? <Pipeline steps={steps} compact /> : <div className="text-xs text-muted">Waiting to start…</div>}
            <div className="mt-3 text-[11px] leading-snug text-muted">DETECT → UNDERSTAND → PREDICT → PRIORITISE → PLAN → DISPATCH → VERIFY → LEARN</div></div>
          <div className="space-y-1.5 text-xs">
            {state === "idle" && <p className="text-muted">Runs the whole loop on the Kerala Flood Demo: alert → simulated satellite acquisition → detection → impact → priority → prediction → route → resource allocation → field verification → recalculated priority. Takes about a minute and creates a new demo event.</p>}
            {lines.map((l, i) => <p key={i} className={color[l.tone || "info"]}><span className="mr-1 tabular-nums text-muted">{String(i + 1).padStart(2, "0")}</span>{l.t}</p>)}
            {state === "running" && <p className="pulse-dot text-accent">● working…</p>}
            {final && (
              <div className="mt-2 flex items-center gap-2 rounded border border-ok/40 bg-ok/10 p-2">
                <LevelBadge level={final.fr.before.level} /><span>→</span><LevelBadge level={final.fr.after.level} /><span className="text-ok">FIELD VERIFIED · closed loop complete</span>
              </div>
            )}
          </div>
        </div>
        <footer className="flex items-center justify-between border-t border-line px-4 py-2.5">
          <span className="text-[11px] text-muted">AI assists decisions; it is not an autonomous authority.</span>
          <div className="flex gap-2">
            {state === "idle" && <button className="btn btn-primary" onClick={run}>Start demo</button>}
            {state === "error" && <button className="btn btn-primary" onClick={run}>Retry</button>}
            {eid && <Link href={`/events/${eid}/map`} className="btn">Open map</Link>}
            {state === "done" && eid && <Link href={`/events/${eid}/reports`} className="btn btn-primary">Situation report</Link>}
            {state === "done" && eid && <Link href={`/events/${eid}/present`} className="btn">Presentation mode</Link>}
          </div>
        </footer>
      </div>
    </div>
  );
}
