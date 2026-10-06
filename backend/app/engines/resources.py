"""Resource command: explainable allocation of rescue resources to priority cells + coverage simulation."""
from __future__ import annotations

import math
from typing import Callable

KIND_ORDER = ["rescue_team", "boat", "ambulance", "medical_team", "drone", "relief_vehicle"]
KIND_LABEL = {"rescue_team": "Rescue Team", "boat": "Boat", "ambulance": "Ambulance", "medical_team": "Medical Team",
              "drone": "Drone", "relief_vehicle": "Relief Vehicle"}
CORE_KINDS = ("rescue_team", "boat")  # needed for a P1 cell to count as "served"


def requirements_for_cell(c: dict, hazard: str) -> list[dict]:
    """Rule-based, inspectable requirements. Each entry says why it exists."""
    lvl = c["priority_level"]
    exp = c.get("population_exposed", 0)
    req: list[dict] = []
    water_hazard = hazard in ("flood", "cyclone")
    if lvl == "P1":
        n = max(1, min(3, math.ceil(exp / 1500)))
        req.append({"kind": "rescue_team", "qty": n, "why": f"P1 with {exp:,} people exposed"})
    elif lvl == "P2" and exp >= 300:
        req.append({"kind": "rescue_team", "qty": 1, "why": f"P2 with {exp:,} people exposed"})
    if water_hazard and lvl == "P1" and (c.get("severity", 0) >= 0.6 or c.get("access_loss", 0) >= 0.5 or c.get("isolated")):
        why = "road access lost / community isolated" if (c.get("access_loss", 0) >= 0.5 or c.get("isolated")) else "severe inundation"
        req.append({"kind": "boat", "qty": 2 if exp >= 2500 else 1, "why": why})
    if lvl in ("P1", "P2") and (c.get("hospitals", 0) or c.get("vulnerable_population", 0) >= 200):
        req.append({"kind": "ambulance", "qty": 1, "why": "hospital at risk" if c.get("hospitals") else f"{c.get('vulnerable_population', 0):,} vulnerable people"})
    if lvl == "P1" and (c.get("vulnerable_population", 0) >= 250 or c.get("hospitals", 0)):
        req.append({"kind": "medical_team", "qty": 1, "why": "vulnerable population / hospital continuity"})
    if lvl in ("P1", "P2") and (c.get("confidence", 1) < 0.6 or c.get("road_status") == "unknown"):
        req.append({"kind": "drone", "qty": 1, "why": "low confidence / unknown access - aerial assessment"})
    if lvl == "P2" and exp >= 150:
        req.append({"kind": "relief_vehicle", "qty": 1, "why": "relief & evacuation staging within 6-12 h"})
    return req


def allocate(cells: list[dict], resources: list[dict], eta_fn: Callable[[dict, dict], float], hazard: str,
             levels=("P1", "P2")) -> dict:
    """cells: priority cells (any level); resources: id, kind, name, status, ... Only status=='available' are used.
    Pass 1 gives every cell its first unit of each required kind (so scarce teams cover more P1s);
    pass 2 adds additional units."""
    pool = {k: [r for r in resources if r["kind"] == k and r.get("status", "available") == "available"] for k in KIND_ORDER}
    used: set[int] = set()
    order = sorted([c for c in cells if c["priority_level"] in levels], key=lambda c: (c["priority_level"], -c["priority_score"]))
    reqs = {c["h3_index"]: requirements_for_cell(c, hazard) for c in order}
    assignments: list[dict] = []
    unmet: list[dict] = []

    def pick(kind, cell):
        cands = [r for r in pool[kind] if r["id"] not in used]
        if not cands:
            return None, None
        best = min(cands, key=lambda r: eta_fn(r, cell))
        return best, eta_fn(best, cell)

    def assign(cell, kind, why, unit_no, total):
        r, eta = pick(kind, cell)
        if r is None:
            return False
        used.add(r["id"])
        assignments.append({
            "resource_id": r["id"], "resource": r["name"], "kind": kind, "h3_index": cell["h3_index"], "cell_no": cell.get("cell_no"),
            "priority_level": cell["priority_level"], "eta_min": round(float(eta), 1),
            "reason": f"{KIND_LABEL[kind]} -> Cell {cell.get('cell_no')} ({cell['priority_level']}): {why}. Unit {unit_no}/{total}; nearest available (ETA {eta:.0f} min).",
        })
        return True

    for pass_no in (1, 2):
        for c in order:
            for rq in reqs[c["h3_index"]]:
                have = sum(1 for a in assignments if a["h3_index"] == c["h3_index"] and a["kind"] == rq["kind"])
                targets = range(have + 1, (2 if pass_no == 1 else rq["qty"] + 1))
                for u in targets:
                    if u > rq["qty"]:
                        break
                    if not assign(c, rq["kind"], rq["why"], u, rq["qty"]):
                        unmet.append({"h3_index": c["h3_index"], "cell_no": c.get("cell_no"), "priority_level": c["priority_level"],
                                      "kind": rq["kind"], "missing": rq["qty"] - have, "why": rq["why"]})
                        break
    # de-duplicate unmet records per (cell, kind)
    seen, dedup = set(), []
    for u in unmet:
        key = (u["h3_index"], u["kind"])
        if key not in seen:
            seen.add(key)
            dedup.append(u)
    by_cell: dict[str, list[dict]] = {}
    for a in assignments:
        by_cell.setdefault(a["h3_index"], []).append(a)
    p1 = [c for c in order if c["priority_level"] == "P1"]
    served, unserved, first_etas = [], [], []
    for c in p1:
        got = {a["kind"] for a in by_cell.get(c["h3_index"], [])}
        needs = {rq["kind"] for rq in reqs[c["h3_index"]] if rq["kind"] in CORE_KINDS}
        if needs and needs <= got:
            served.append(c)
            first_etas.append(min(a["eta_min"] for a in by_cell[c["h3_index"]] if a["kind"] in CORE_KINDS))
        else:
            unserved.append({"h3_index": c["h3_index"], "cell_no": c.get("cell_no"), "missing": sorted(needs - got)})
    first_etas.sort()
    metrics = {
        "p1_total": len(p1), "p1_served": len(served),
        "p1_coverage_pct": round(100 * len(served) / len(p1), 1) if p1 else None,
        "unserved_p1": unserved, "unserved_p1_count": len(unserved),
        "est_response_delay_min": round(first_etas[-1], 1) if first_etas else None,
        "mean_first_response_min": round(sum(first_etas) / len(first_etas), 1) if first_etas else None,
        "units_assigned": len(assignments),
        "units_available": {k: len(pool[k]) for k in KIND_ORDER},
        "note": "Estimates from rule-based requirements and graph ETAs; not a dispatch guarantee.",
    }
    return {"assignments": assignments, "unmet": dedup, "metrics": metrics}


def scale_roster(resources: list[dict], counts: dict[str, int], bases: list[dict]) -> list[dict]:
    """Build a what-if roster with exactly `counts[kind]` available units per kind (extra units spawn at bases)."""
    out: list[dict] = []
    nid = -1
    for kind in KIND_ORDER:
        have = [r for r in resources if r["kind"] == kind]
        want = counts.get(kind, len([r for r in have if r.get("status") == "available"]))
        pick = have[:want]
        out.extend({**r, "status": "available"} for r in pick)
        for i in range(len(pick), want):
            b = bases[i % len(bases)]
            template = have[0] if have else {"speed_kmh": 35}
            out.append({"id": nid, "kind": kind, "name": f"{KIND_LABEL[kind]} {i + 1:02d} (what-if)", "status": "available",
                        "lat": b["lat"], "lon": b["lon"], "speed_kmh": template.get("speed_kmh", 35)})
            nid -= 1
    return out
