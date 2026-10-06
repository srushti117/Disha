"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import { download } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { useEvent } from "@/components/EventContext";
import { Disclosure, Empty, ErrorBox, PageHeader, Panel } from "@/components/ui";
import { FreshnessList } from "@/components/Insights";

const EXPORTS = [
  ["geojson", "GeoJSON", "Cells with priority, confidence, reasons + metadata"], ["kml", "KML", "Google Earth / offline field maps"], ["csv", "CSV", "Spreadsheet table of all cells"],
  ["pdf", "PDF", "Situation report"], ["cog", "COG (severity)", "Cloud Optimized GeoTIFF of the severity raster"],
] as const;

export default function Reports() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const { event } = useEvent();
  const version = event?.assessment_version ?? 0;
  const { data: sum } = useApi<any>(`/api/events/${id}/summary`, { deps: [version] });
  const { data: health } = useApi<any>(`/api/events/${id}/data-health`, { deps: [version] });
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!version) return <Empty>Run analysis to generate reports and exports.</Empty>;
  async function get(fmt: string) {
    setBusy(fmt); setErr(null);
    try {
      if (fmt === "pdf") await download(`/api/events/${id}/report`, `DISHA_${event?.code}_situation_report.pdf`);
      else await download(`/api/events/${id}/export?format=${fmt}`, `${event?.code}.${fmt === "cog" ? "tif" : fmt}`);
    } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  }
  return (
    <div className="space-y-6">
      <PageHeader title="Reports & exports" sub="Download a situation report or the data behind it" />
      <ErrorBox error={err} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Situation report (PDF)" className="lg:col-span-1">
          <p className="mb-3 text-xs text-muted">A readable summary with the map, priority areas, affected facilities, planned resources and the data sources used.</p>
          <button className="btn btn-primary w-full" disabled={!can("report.generate") || busy === "pdf"} onClick={() => get("pdf")}>{busy === "pdf" ? "Generating…" : "Download situation report (PDF)"}</button>
          {!can("report.generate") && <p className="mt-1 text-[11px] text-muted">Your role cannot generate reports.</p>}
        </Panel>
        <Panel title="Data exports" className="lg:col-span-2">
          <div className="grid gap-2 sm:grid-cols-2">
            {EXPORTS.filter(([k]) => k !== "pdf").map(([k, l, d]) => (
              <button key={k} className="rounded border border-line bg-panel2 p-2.5 text-left hover:border-accent disabled:opacity-50" disabled={busy === k} onClick={() => get(k)}>
                <div className="text-xs font-bold text-strong">{busy === k ? "Preparing…" : l}</div><div className="text-xs text-muted">{d}</div>
              </button>
            ))}
          </div>
        </Panel>
      </div>
      <Disclosure title="Summary text and data freshness">
        <p className="text-[15px] leading-relaxed">{sum?.text}</p>
        {health && <div className="mt-5"><div className="mb-1.5 text-sm font-medium text-strong">Data freshness</div><FreshnessList items={health.freshness} /></div>}
      </Disclosure>
    </div>
  );
}
