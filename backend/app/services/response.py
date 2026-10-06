"""Response planning: routes, evacuation, resource allocation + simulation (all driven by DB state)."""
from __future__ import annotations

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..engines import resources as res_engine
from ..engines import routing
from ..engines.evacuation import plan_evacuation
from ..engines.geo import haversine_m
from ..models import Event, H3Cell, Resource, ResourceAssignment, RoadSegment, Route, Shelter
from .common import now


def load_segments(db: Session, event_id: int) -> list[dict]:
    out = []
    for r in db.scalars(select(RoadSegment).where(RoadSegment.event_id == event_id)):
        out.append({"id": r.id, "name": r.name, "class": r.road_class, "u": r.u, "v": r.v, "length_m": r.length_m, "is_bridge": r.is_bridge,
                    "status": r.status, "h3_indices": r.h3_indices, "is_critical": r.is_critical, "flooded_fraction": r.flooded_fraction,
                    "coords": r.geom["coordinates"]})
    return out


def load_graph(db: Session, event: Event):
    nodes = {int(k): tuple(v) for k, v in event.config.get("road_nodes", {}).items()}
    segs = load_segments(db, event.id)
    sev = {c.h3_index: c.severity for c in db.scalars(select(H3Cell).where(H3Cell.event_id == event.id))}
    return routing.build_graph(segs, sev), nodes, segs


def cell_node(G, nodes, cell: H3Cell, prefer_reachable_from: set[int] | None = None):
    return routing.nearest_node(nodes, cell.lat, cell.lon, G)


def compute_routes(db: Session, event: Event, target_h3: str, origin: tuple[float, float] | None = None, persist: bool = True) -> dict:
    cell = db.scalars(select(H3Cell).where(H3Cell.event_id == event.id, H3Cell.h3_index == target_h3)).first()
    if cell is None:
        raise KeyError(target_h3)
    G, nodes, segs = load_graph(db, event)
    bases = event.config.get("bases", [])
    if origin is None:
        if not bases:
            raise ValueError("No response base or origin available")
        origin = (bases[0]["lat"], bases[0]["lon"])
    on, od = routing.nearest_node(nodes, origin[0], origin[1], G)
    tn, td = routing.nearest_node(nodes, cell.lat, cell.lon, G)
    opts = routing.route_options(G, nodes, on, tn)
    last_mile = round(td)
    water = event.hazard in ("flood", "cyclone")
    note = ""
    if cell.severity >= 0.5 and td > 250:
        note = f"Final {last_mile} m to the cell centre crosses the hazard zone: " + ("use boat / high-clearance vehicle." if water else "proceed on foot with hazard assessment.")
    routes_out = []
    if persist:
        db.query(Route).filter(Route.event_id == event.id, Route.target_h3 == target_h3).delete()
    for kind, r in opts["routes"].items():
        rec = r.kind == opts["recommended"]
        rd = r.to_dict()
        rd.update({"recommended": rec, "label": {"shortest": "Route A (shortest)", "fastest": "Route B (fastest)", "safest": "Route C (safest)"}[kind],
                   "last_mile_m": last_mile, "last_mile_note": note})
        routes_out.append(rd)
        if persist and r.node_path:
            db.add(Route(event_id=event.id, target_h3=target_h3, origin_lat=origin[0], origin_lon=origin[1], kind=kind,
                         geom={"type": "LineString", "coordinates": r.coords} if len(r.coords) >= 2 else None, distance_km=r.distance_km, eta_min=r.eta_min,
                         risk=r.risk, blocked_segments=r.blocked_segments, feasible=r.feasible, recommended=rec,
                         notes=("; ".join(r.segment_names) + (" | " + note if note else "")).strip(" |"), version=event.assessment_version))
    return {"target": {"h3_index": target_h3, "cell_no": cell.cell_no, "priority_level": cell.priority_level}, "origin": {"lat": origin[0], "lon": origin[1], "snapped_m": round(od)},
            "routes": routes_out, "recommended": opts["recommended"], "summary": routing.explain(opts), "last_mile_note": note,
            "isolated_target": bool(cell.population_isolated), "generated_at": now().isoformat(), "assessment_version": event.assessment_version}


def precompute_routes(db: Session, event: Event, top_n: int = 6) -> int:
    top = db.scalars(select(H3Cell).where(H3Cell.event_id == event.id, H3Cell.priority_level == "P1").order_by(H3Cell.cell_no).limit(top_n)).all()
    n = 0
    for c in top:
        try:
            compute_routes(db, event, c.h3_index)
            n += 1
        except Exception:
            continue
    return n


def evacuation_plan(db: Session, event: Event) -> dict:
    G, nodes, _ = load_graph(db, event)
    cells = db.scalars(select(H3Cell).where(H3Cell.event_id == event.id, H3Cell.population_exposed > 0)).all()
    shelters = db.scalars(select(Shelter).where(Shelter.event_id == event.id)).all()
    cn, sn = {}, {}
    for c in cells:
        try:
            cn[c.h3_index] = routing.nearest_node(nodes, c.lat, c.lon, G)[0]
        except ValueError:
            cn[c.h3_index] = None
    for s in shelters:
        la, lo = s.geom["coordinates"][1], s.geom["coordinates"][0]
        sn[s.id] = routing.nearest_node(nodes, la, lo, G)[0] if nodes else None
    plan = plan_evacuation(
        [{"h3_index": c.h3_index, "cell_no": c.cell_no, "priority_level": c.priority_level, "priority_score": c.priority_score,
          "population_exposed": c.population_exposed, "isolated": c.population_isolated > 0} for c in cells],
        [{"id": s.id, "name": s.name, "capacity": s.capacity, "occupied": s.occupied, "in_hazard_zone": s.in_hazard_zone} for s in shelters], G, cn, sn)
    plan["shelters"] = [{"id": s.id, "name": s.name, "lat": s.geom["coordinates"][1], "lon": s.geom["coordinates"][0], "capacity": s.capacity,
                         "occupied": s.occupied, "in_hazard_zone": s.in_hazard_zone} for s in shelters]
    return plan


# ----------------------------------------------------------------------------- resources


def _roster(db: Session, event_id: int) -> list[dict]:
    return [{"id": r.id, "kind": r.kind, "name": r.name, "status": r.status, "lat": r.lat, "lon": r.lon, "speed_kmh": r.speed_kmh, "assigned_cell": r.assigned_cell}
            for r in db.scalars(select(Resource).where(Resource.event_id == event_id).order_by(Resource.kind, Resource.name))]


def _cell_dicts(db: Session, event_id: int) -> list[dict]:
    return [{"h3_index": c.h3_index, "cell_no": c.cell_no, "priority_level": c.priority_level, "priority_score": c.priority_score,
             "population_exposed": c.population_exposed, "vulnerable_population": c.vulnerable_population, "severity": c.severity,
             "access_loss": c.access_loss, "road_status": c.road_status, "hospitals": (c.components.get("facility_counts") or {}).get("hospital_near", 0),
             "confidence": c.confidence, "isolated": c.population_isolated > 0, "lat": c.lat, "lon": c.lon}
            for c in db.scalars(select(H3Cell).where(H3Cell.event_id == event_id))]


def make_eta_fn(db: Session, event: Event):
    G, nodes, _ = load_graph(db, event)
    usable = nx.Graph(((u, v, d) for u, v, d in G.edges(data=True) if d["status"] != "blocked"))
    cache: dict[int, dict] = {}

    def eta(res: dict, cell: dict) -> float:
        straight = haversine_m(res["lat"], res["lon"], cell["lat"], cell["lon"]) / 1000
        if res["kind"] in ("drone",):
            return straight / res["speed_kmh"] * 60
        if res["kind"] == "boat":
            return straight * 1.25 / res["speed_kmh"] * 60 + 4
        try:
            a, _ = routing.nearest_node(nodes, res["lat"], res["lon"], usable)
            b, bd = routing.nearest_node(nodes, cell["lat"], cell["lon"], usable)
        except ValueError:
            return straight * 1.6 / res["speed_kmh"] * 60
        if a not in cache:
            cache[a] = nx.single_source_dijkstra_path_length(usable, a, weight="time_min") if a in usable else {}
        t = cache[a].get(b)
        if t is None:
            return straight * 2.2 / res["speed_kmh"] * 60 + 20  # no open road: penalised detour estimate
        return t * (35 / max(res["speed_kmh"], 1)) + bd / 1000 / 20 * 60

    return eta


def allocation(db: Session, event: Event, counts: dict | None = None, commit: bool = False, user=None) -> dict:
    cells = _cell_dicts(db, event.id)
    roster = _roster(db, event.id)
    if counts is not None:
        roster = res_engine.scale_roster(roster, counts, event.config.get("bases", []))
    else:
        roster = [r for r in roster if r["status"] == "available"]
    out = res_engine.allocate(cells, roster, make_eta_fn(db, event), event.hazard)
    out["resources_considered"] = len(roster)
    out["simulated"] = counts is not None
    if commit and counts is None:
        db.query(ResourceAssignment).filter(ResourceAssignment.event_id == event.id, ResourceAssignment.status == "recommended").delete()
        for a in out["assignments"]:
            db.add(ResourceAssignment(event_id=event.id, resource_id=a["resource_id"], h3_index=a["h3_index"], reason=a["reason"], eta_min=a["eta_min"],
                                      status="recommended", assigned_by=getattr(user, "id", None)))
    return out


def resource_summary(db: Session, event_id: int) -> dict:
    roster = _roster(db, event_id)
    kinds = res_engine.KIND_ORDER
    avail = {k: sum(1 for r in roster if r["kind"] == k and r["status"] == "available") for k in kinds}
    dep = {k: sum(1 for r in roster if r["kind"] == k and r["status"] == "deployed") for k in kinds}
    p1 = db.query(H3Cell).filter(H3Cell.event_id == event_id, H3Cell.priority_level == "P1").all()
    deployed_cells = {a.h3_index for a in db.scalars(select(ResourceAssignment).where(ResourceAssignment.event_id == event_id, ResourceAssignment.status.in_(["dispatched"])))}
    unassigned = [c for c in p1 if c.h3_index not in deployed_cells]
    return {"available": avail, "deployed": dep, "unassigned_p1": [{"h3_index": c.h3_index, "cell_no": c.cell_no} for c in unassigned], "p1_total": len(p1),
            "roster": roster}
