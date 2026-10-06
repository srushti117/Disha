"use client";
import Link from "next/link";
import { PageHeader, Panel } from "@/components/ui";

const STEPS = [
  ["An alert comes in", "A disaster happens (for example the 2018 Kerala floods) and the affected area is defined on the map."],
  ["Satellite images are compared", "Radar and optical satellite images from before and after the event are compared. Where water, burn scars or ground change shows up, DISHA flags it."],
  ["The area is split into hexagon cells", "The map is divided into hexagons about 500 m across. For each cell DISHA works out how many people live there, whether there is a hospital or school, and whether the roads still work."],
  ["Each cell gets a priority", "Cells are ranked P1 (most urgent) to P4 (least urgent) and the app always shows the reasons behind a ranking."],
  ["It estimates what happens next", "Heuristic estimates for the next 6, 12, 24 and 48 hours show which cells may get worse. These are estimates, not forecasts you can rely on."],
  ["It proposes a response plan", "Which road is safe to use, which teams, boats and ambulances to send where, and which shelters can take the people who need to move."],
  ["The field confirms", "A responder on the ground sends a report or photo. DISHA recalculates the priority, so the plan stays tied to what is actually happening."],
];

const LEVELS = [["P1", "#d62f35", "Critical", "Send rescue and medical teams immediately"], ["P2", "#e0721a", "High", "Relief or evacuation within 6 to 12 hours"], ["P3", "#d9a400", "Moderate", "Ground assessment and supplies"], ["P4", "#6b7a90", "Low", "Monitor; check again on the next satellite pass"]];

const GLOSSARY = [
  ["Cell", "One hexagon on the map (about 500 m). \"Cell 07\" is hexagon number 7."],
  ["Priority score", "A number from 0 to 1: 35% how severe the hazard is, 30% how many people are affected, 20% critical places such as hospitals, 15% how badly road access is cut. Higher means more urgent."],
  ["Confidence", "How much the system trusts its own result (high, medium or low). Low confidence means verify on the ground first."],
  ["SAR (radar)", "Radar satellites such as Sentinel-1 see through cloud and at night, which is why floods are analysed radar-first."],
  ["Estimate", "A prediction rather than a measurement. Always labelled, always with a probability."],
  ["Field verified", "A responder confirmed the situation on the ground. This can change a cell's priority."],
  ["Real data / Simulated", "Events marked Real data use actual open satellite, map and population data. Events marked Simulated use generated data for demonstration."],
];

export default function Guide() {
  return (
    <div className="mx-auto max-w-4xl space-y-6 px-6 py-8">
      <PageHeader title="How DISHA works" sub="A two-minute explanation" />

      <Panel title="What is DISHA?">
        <p className="text-sm leading-relaxed">
          After a flood, wildfire, landslide or cyclone, response teams need to know: <b className="text-strong">where to go first, what to do there, which resources to send, which road to take, and why.</b>
        </p>
        <p className="mt-2 text-sm leading-relaxed">
          DISHA reads satellite images to find where the damage is, combines that with population, hospitals and roads, and produces a ranked list of places to reach first, with the reasons shown for every ranking.
        </p>
        <div className="mt-3 rounded-md border border-warn/40 bg-warn/10 p-3 text-xs text-warn">
          <b>Prototype.</b> This is a decision-support prototype, not an operational emergency system. Events marked <b>Real data</b> use open Sentinel, OpenStreetMap and WorldPop data, but population is a modelled estimate, shelter capacities and the response-unit roster are assumptions, and the models have not been validated against ground truth.
        </div>
      </Panel>

      <Panel title="The process">
        <ol className="space-y-2.5">
          {STEPS.map(([t, d], i) => (
            <li key={t} className="flex gap-3">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent text-xs font-semibold text-white">{i + 1}</span>
              <div><div className="text-sm font-semibold text-strong">{t}</div><div className="text-[13px] text-muted">{d}</div></div>
            </li>
          ))}
        </ol>
      </Panel>

      <Panel title="Priority levels">
        <div className="grid gap-2 md:grid-cols-2">
          {LEVELS.map(([p, c, n, d]) => (
            <div key={p} className="flex items-center gap-3 rounded-md border border-line p-2.5">
              <span className="rounded px-2.5 py-1 text-sm font-bold text-white" style={{ background: c }}>{p}</span>
              <div><div className="text-sm font-semibold text-strong">{n}</div><div className="text-xs text-muted">{d}</div></div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Try it in three clicks">
        <ol className="list-decimal space-y-1.5 pl-5 text-sm">
          <li>Open <Link href="/events" className="font-medium text-accent underline">Events</Link> and start the <b className="text-strong">Kerala floods 2018 - Kuttanad (real data)</b> scenario. The first run downloads real satellite and map data and takes a couple of minutes.</li>
          <li>Press <b className="text-strong">Analyse event</b> and watch the pipeline steps complete.</li>
          <li>Open the <b className="text-strong">Map</b>, click any hexagon to see why it has its priority, and use the time slider to see the estimated situation hours ahead.</li>
        </ol>
        <p className="mt-2 text-xs text-muted">For a fast guided tour with simulated data, use <Link href="/command-center" className="text-accent underline">Command Centre</Link> and choose Run DISHA demo.</p>
      </Panel>

      <Panel title="Glossary" pad={false}>
        <dl className="divide-y divide-line">
          {GLOSSARY.map(([k, v]) => <div key={k} className="grid gap-1 px-3.5 py-2.5 md:grid-cols-[11rem_1fr]"><dt className="text-sm font-semibold text-strong">{k}</dt><dd className="text-[13px] text-muted">{v}</dd></div>)}
        </dl>
      </Panel>
    </div>
  );
}
