"""Evacuation planner: assigns at-risk population to reachable, safe shelters with finite capacity."""
from __future__ import annotations

import networkx as nx


def plan_evacuation(cells: list[dict], shelters: list[dict], G: nx.Graph, cell_node: dict[str, int | None],
                    shelter_node: dict[int, int | None], levels=("P1", "P2")) -> dict:
    """cells: h3_index, cell_no, priority_level, priority_score, population_exposed, isolated(bool)
    shelters: id, name, capacity, occupied, in_hazard_zone. Returns assignments + flags (never silently drops people)."""
    usable = nx.Graph(((u, v, d) for u, v, d in G.edges(data=True) if d["status"] != "blocked"))
    remaining = {s["id"]: max(0, s["capacity"] - s["occupied"]) for s in shelters}
    safe = [s for s in shelters if not s["in_hazard_zone"]]
    todo = sorted([c for c in cells if c["priority_level"] in levels and c["population_exposed"] > 0], key=lambda c: -c["priority_score"])
    assignments, flags = [], []
    cache: dict[int, dict] = {}

    def dists(src):
        if src not in cache:
            cache[src] = nx.single_source_dijkstra_path_length(usable, src, weight="length") if src in usable else {}
        return cache[src]

    total_need = total_assigned = 0
    for c in todo:
        need = int(c["population_exposed"])
        total_need += need
        src = cell_node.get(c["h3_index"])
        cand = []
        if src is not None:
            d = dists(src)
            for s in safe:
                sn = shelter_node.get(s["id"])
                if sn in d:
                    cand.append((d[sn], s))
        cand.sort(key=lambda x: x[0])
        if not cand:
            flags.append({"type": "unreachable_shelter", "cell": c["h3_index"], "cell_no": c.get("cell_no"),
                          "detail": f"No safe shelter reachable by open road from cell {c.get('cell_no')}; {need:,} people need air/boat evacuation."})
            continue
        for dist_m, s in cand:
            if need <= 0:
                break
            take = min(need, remaining[s["id"]])
            if take <= 0:
                continue
            remaining[s["id"]] -= take
            need -= take
            total_assigned += take
            assignments.append({"h3_index": c["h3_index"], "cell_no": c.get("cell_no"), "priority_level": c["priority_level"],
                                "shelter_id": s["id"], "shelter_name": s["name"], "people": take,
                                "distance_km": round(dist_m / 1000, 2), "capacity_available_after": remaining[s["id"]]})
        if need > 0:
            flags.append({"type": "insufficient_capacity", "cell": c["h3_index"], "cell_no": c.get("cell_no"),
                          "detail": f"{need:,} people from cell {c.get('cell_no')} have no shelter capacity left."})
    for s in shelters:
        used = s["capacity"] - remaining[s["id"]]
        if s["in_hazard_zone"]:
            flags.append({"type": "shelter_in_hazard_zone", "shelter": s["name"], "detail": f"{s['name']} lies inside the hazard zone and is excluded."})
        elif s["capacity"] and used / s["capacity"] >= 0.95:
            flags.append({"type": "overcapacity", "shelter": s["name"], "detail": f"{s['name']} is at {used / s['capacity']:.0%} of capacity."})
    return {
        "assignments": assignments, "flags": flags,
        "summary": {"people_needing_shelter": total_need, "people_assigned": total_assigned, "shortfall": total_need - total_assigned,
                    "shelter_utilisation": [{"id": s["id"], "name": s["name"], "capacity": s["capacity"], "assigned_now": s["capacity"] - s["occupied"] - remaining[s["id"]],
                                             "available_after": remaining[s["id"]], "in_hazard_zone": s["in_hazard_zone"]} for s in shelters]},
    }
