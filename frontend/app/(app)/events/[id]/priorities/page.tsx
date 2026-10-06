"use client";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { LEVEL_COLOR, pct } from "@/lib/format";
import { useEvent } from "@/components/EventContext";
import CellPanel from "@/components/CellPanel";
import { ConfBadge, Empty, ErrorBox, LevelBadge, PageHeader, Panel, Spinner } from "@/components/ui";

const KEYS = ["severity", "exposure", "infrastructure", "accessibility"] as const;
const LABEL = { severity: "Severity (S)", exposure: "Exposure (E)", infrastructure: "Critical infra (C)", accessibility: "Access loss (A)" };

function Inner() {
  const { id } = useParams<{ id: string }>();
  const sp = useSearchParams();
  const { can } = useAuth();
  const { event } = useEvent();
  const version = event?.assessment_version ?? 0;
  const [levels, setLevels] = useState<string[]>(["P1", "P2", "P3"]);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const { data, loading, reload } = useApi<any>(`/api/events/${id}/priorities?level=${levels.join(",")}${q ? `&q=${encodeURIComponent(q)}` : ""}&limit=300`, { deps: [version] });
  const [w, setW] = useState<Record<string, number> | null>(null);
  const [th, setTh] = useState<Record<string, number> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => { if (data && !w) { setW(data.weights); setTh(data.thresholds); } }, [data, w]);
  useEffect(() => {
    const c = sp.get("cell");
    if (c && data) { const m = data.cells.find((x: any) => String(x.cell_no) === c); if (m) setSel(m.h3_index); }
  }, [sp, data]);

  async function save(reset = false) {
    setSaving(true); setErr(null);
    try {
      const body = reset ? { weights: data.default_weights, thresholds: data.default_thresholds } : { weights: w, thresholds: th };
      await api(`/api/events/${id}/priorities/config`, { method: "PUT", body });
      setW(null); reload();
    } catch (e: any) { setErr(e.message); } finally { setSaving(false); }
  }

  if (!version) return <Empty>Run analysis to generate priorities.</Empty>;
  const sum = w ? Object.values(w).reduce((a, b) => a + b, 0) : 1;
  return (
    <div>
      <PageHeader title="Priorities" sub="Impact Priority Index: PI = wS·S + wE·E + wC·C + wA·A, all inputs normalised 0-1" />
      <div className="grid gap-4 xl:grid-cols-[1fr_22rem]">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            {["P1", "P2", "P3", "P4"].map((l) => {
              const on = levels.includes(l);
              return <button key={l} onClick={() => setLevels(on ? levels.filter((x) => x !== l) : [...levels, l])} className="rounded border px-2.5 py-1 text-xs font-bold" style={{ borderColor: LEVEL_COLOR[l], background: on ? `${LEVEL_COLOR[l]}33` : "transparent", color: LEVEL_COLOR[l] }}>{l} <span className="tabular-nums">{data?.counts[l] ?? ""}</span></button>;
            })}
            <input className="input ml-auto max-w-xs" placeholder="Search cell no. or reason…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          {loading && !data ? <Spinner /> : (
            <div className="panel overflow-x-auto">
              <table className="w-full">
                <thead><tr className="border-b border-line"><th className="th">Cell</th><th className="th">Level</th><th className="th">PI</th><th className="th">S / E / C / A</th><th className="th">Confidence</th><th className="th">Exposed</th><th className="th">Road</th><th className="th">Field</th><th className="th">Top reasons</th></tr></thead>
                <tbody>
                  {data?.cells.map((c: any) => (
                    <tr key={c.h3_index} onClick={() => setSel(c.h3_index)} className={`cursor-pointer border-b border-line/60 hover:bg-panel2 ${sel === c.h3_index ? "bg-panel2" : ""}`}>
                      <td className="td tabular-nums font-bold text-strong">{String(c.cell_no).padStart(2, "0")}</td>
                      <td className="td"><LevelBadge level={c.level} small /></td>
                      <td className="td tabular-nums">{c.score.toFixed(2)}</td>
                      <td className="td tabular-nums text-xs text-muted">{KEYS.map((k) => Math.round((c.components[k] || 0) * 100)).join(" / ")}</td>
                      <td className="td"><ConfBadge value={c.confidence} label={c.confidence_label.replace(" CONFIDENCE", "")} /></td>
                      <td className="td tabular-nums">{c.population_exposed.toLocaleString()}</td>
                      <td className="td text-muted">{c.road_status.replace("_", " ")}</td>
                      <td className="td text-xs text-muted">{c.field_status}</td>
                      <td className="td text-xs text-muted">{c.reason_codes.slice(0, 2).join(" · ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!data?.cells.length && <div className="p-4 text-xs text-muted">No cells match.</div>}
            </div>
          )}
          {can("priority.configure") && w && th && (
            <Panel title="Priority engine configuration" right={<span className="text-[11px] text-muted">changes recalculate the whole event and are audit-logged</span>}>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-2">
                  <div className="label">Weights (normalised to {sum.toFixed(2)} → 1.00)</div>
                  {KEYS.map((k) => (
                    <div key={k} className="flex items-center gap-2 text-xs"><span className="w-32 text-muted">{LABEL[k]}</span>
                      <input type="range" min={0} max={1} step={0.05} value={w[k]} onChange={(e) => setW({ ...w, [k]: +e.target.value })} className="flex-1 accent-accent" /><span className="w-12 text-right tabular-nums">{(w[k] / sum).toFixed(2)}</span></div>
                  ))}
                </div>
                <div className="space-y-2">
                  <div className="label">Level thresholds (PI ≥)</div>
                  {["P1", "P2", "P3"].map((k) => (
                    <div key={k} className="flex items-center gap-2 text-xs"><span className="w-10 font-bold" style={{ color: LEVEL_COLOR[k] }}>{k}</span>
                      <input type="range" min={0.05} max={0.95} step={0.01} value={th[k]} onChange={(e) => setTh({ ...th, [k]: +e.target.value })} className="flex-1 accent-accent" /><span className="w-12 text-right tabular-nums">{th[k].toFixed(2)}</span></div>
                  ))}
                </div>
              </div>
              <ErrorBox error={err} />
              <div className="mt-3 flex gap-2"><button className="btn btn-primary" disabled={saving} onClick={() => save(false)}>{saving ? "Recalculating…" : "Apply & recalculate"}</button><button className="btn" disabled={saving} onClick={() => save(true)}>Reset to DISHA defaults</button></div>
            </Panel>
          )}
        </div>
        <div className="xl:sticky xl:top-2 xl:self-start">
          {sel ? <div className="max-h-[calc(100vh-9rem)]"><CellPanel eventId={Number(id)} h3={sel} version={version} onClose={() => setSel(null)} canPlan={can("route.plan")} canAssign={can("resource.assign")} canField={can("field.report")} /></div>
            : <Empty>Select a cell to see <b>why</b> it has this priority.</Empty>}
        </div>
      </div>
    </div>
  );
}

export default function Priorities() {
  return <Suspense fallback={<Spinner />}><Inner /></Suspense>;
}
