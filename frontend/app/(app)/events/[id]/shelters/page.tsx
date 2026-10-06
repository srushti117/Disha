"use client";
import { useParams } from "next/navigation";
import { useApi } from "@/lib/hooks";
import { num } from "@/lib/format";
import { useEvent } from "@/components/EventContext";
import { Bar, Empty, LevelBadge, PageHeader, Panel, Spinner, Stat } from "@/components/ui";

const FLAG: Record<string, string> = { unreachable_shelter: "UNREACHABLE", insufficient_capacity: "INSUFFICIENT CAPACITY", overcapacity: "OVERCAPACITY", shelter_in_hazard_zone: "UNSAFE SHELTER" };

export default function Shelters() {
  const { id } = useParams<{ id: string }>();
  const { event } = useEvent();
  const version = event?.assessment_version ?? 0;
  const { data } = useApi<any>(`/api/events/${id}/shelters`, { deps: [version] });
  if (!version) return <Empty>Run analysis to plan evacuation.</Empty>;
  if (!data) return <Spinner />;
  const s = data.summary;
  return (
    <div className="space-y-4">
      <PageHeader title="Evacuation planner" sub="People in P1/P2 cells are assigned to safe, road-reachable shelters with remaining capacity" />
      <div className="panel grid grid-cols-3 gap-3 p-3">
        <Stat label="Need shelter" value={num(s.people_needing_shelter)} /><Stat label="Placed" value={num(s.people_assigned)} color="#35c28a" />
        <Stat label="Shortfall" value={num(s.shortfall)} color={s.shortfall ? "#e5484d" : "#35c28a"} />
      </div>
      {data.flags.length > 0 && (
        <Panel title={`Flags (${data.flags.length})`}>
          <ul className="space-y-1">{data.flags.map((f: any, i: number) => <li key={i} className="flex gap-2 text-xs"><span className="shrink-0 rounded bg-p2/20 px-1.5 py-0.5 text-[11px] font-bold text-p2">{FLAG[f.type] || f.type}</span><span className="text-muted">{f.detail}</span></li>)}</ul>
        </Panel>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Assignments" pad={false}>
          <table className="w-full"><thead><tr className="border-b border-line"><th className="th">Cell</th><th className="th">→ Shelter</th><th className="th">People</th><th className="th">Road dist.</th><th className="th">Capacity left</th></tr></thead>
            <tbody>{data.assignments.map((a: any, i: number) => (
              <tr key={i} className="border-b border-line/60"><td className="td tabular-nums font-bold text-strong">{String(a.cell_no).padStart(2, "0")} <LevelBadge level={a.priority_level} small /></td><td className="td">{a.shelter_name}</td>
                <td className="td tabular-nums">{num(a.people)}</td><td className="td tabular-nums">{a.distance_km} km</td><td className="td tabular-nums">{num(a.capacity_available_after)}</td></tr>))}</tbody></table>
          {!data.assignments.length && <div className="p-4 text-xs text-muted">No assignments.</div>}
        </Panel>
        <Panel title="Shelter capacity">
          <div className="space-y-3">
            {s.shelter_utilisation.map((u: any) => {
              const used = u.capacity - u.available_after;
              return <Bar key={u.id} label={`${u.name}${u.in_hazard_zone ? " ⚠ in hazard zone" : ""}`} value={u.capacity ? used / u.capacity : 0} color={u.in_hazard_zone ? "#e5484d" : used / u.capacity > 0.9 ? "#f08a24" : "#35c28a"} right={`${num(used)} / ${num(u.capacity)}`} />;
            })}
          </div>
        </Panel>
      </div>
    </div>
  );
}
