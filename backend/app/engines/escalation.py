"""Change escalation + 'What changed?' comparison between two assessment snapshots."""
from __future__ import annotations

from .priority import LEVEL_RANK


def _reasons(prev: dict, cur: dict) -> list[str]:
    r = []
    if cur.get("severity", 0) - prev.get("severity", 0) >= 0.08:
        r.append("Hazard severity increased")
    if cur.get("access_loss", 0) - prev.get("access_loss", 0) >= 0.10:
        r.append("Road access decreased")
    pe0, pe1 = prev.get("population_exposed", 0), cur.get("population_exposed", 0)
    if pe1 > pe0 * 1.1 and pe1 - pe0 >= 20:
        r.append("Population exposure increased")
    if cur.get("infrastructure_score", 0) - prev.get("infrastructure_score", 0) >= 0.1:
        r.append("Critical-infrastructure exposure increased")
    if cur.get("confidence", 0) - prev.get("confidence", 0) >= 0.08:
        r.append("Confidence increased (new evidence)")
    if cur.get("field_status") in ("confirmed", "severe") and prev.get("field_status") != cur.get("field_status"):
        r.append("Confirmed by field responder")
    if cur.get("field_status") == "false_alarm" and prev.get("field_status") != "false_alarm":
        r.append("Field responder reported a false alarm")
    if cur.get("field_status") == "resolved" and prev.get("field_status") != "resolved":
        r.append("Resolved by field team")
    return r or ["Combined small changes in priority components"]


def diff_priorities(prev: dict[str, dict], cur: dict[str, dict], cell_no: dict[str, int] | None = None) -> list[dict]:
    out = []
    for h, c in cur.items():
        p = prev.get(h)
        if not p or p["level"] == c["level"]:
            continue
        up = LEVEL_RANK[c["level"]] < LEVEL_RANK[p["level"]]
        out.append({
            "h3_index": h, "cell_no": (cell_no or {}).get(h), "from": p["level"], "to": c["level"],
            "direction": "escalated" if up else "de-escalated", "reasons": _reasons(p, c),
            "message": f"CELL {(cell_no or {}).get(h, h)} {'ESCALATED' if up else 'DE-ESCALATED'} FROM {p['level']} TO {c['level']}",
        })
    out.sort(key=lambda x: (x["direction"] != "escalated", LEVEL_RANK[x["to"]]))
    return out


def summarise(snaps: dict[str, dict]) -> dict:
    vals = list(snaps.values())
    aff = [v for v in vals if v.get("severity", 0) >= 0.03]
    return {
        "affected_cells": len(aff),
        "affected_area_km2": round(sum(v.get("affected_area_km2", 0) for v in vals), 2),
        "p1": sum(v["level"] == "P1" for v in vals), "p2": sum(v["level"] == "P2" for v in vals),
        "p3": sum(v["level"] == "P3" for v in vals), "p4": sum(v["level"] == "P4" for v in vals),
        "population_at_risk": sum(v.get("population_high_risk", 0) for v in vals),
        "population_exposed": sum(v.get("population_exposed", 0) for v in vals),
        "hospitals_at_risk": sum(1 for v in vals if v.get("hospitals", 0) and v.get("severity", 0) >= 0.1),
        "road_disruptions": sum(v.get("blocked_segments", 0) for v in vals),
    }


def what_changed(prev: dict[str, dict], cur: dict[str, dict], prev_roads_blocked: int, cur_roads_blocked: int) -> dict:
    a, b = summarise(prev), summarise(cur)
    a["road_disruptions"], b["road_disruptions"] = prev_roads_blocked, cur_roads_blocked
    d = {k: b[k] - a[k] for k in b}

    def pct(x, y):
        return None if not x else round(100 * (y - x) / x, 1)

    return {
        "previous": a, "current": b, "delta": d,
        "pct": {"affected_area": pct(a["affected_area_km2"], b["affected_area_km2"]),
                "population_at_risk": pct(a["population_at_risk"], b["population_at_risk"])},
        "lines": [
            f"{d['affected_cells']:+d} affected cells", f"{d['p1']:+d} P1 locations", f"{d['hospitals_at_risk']:+d} hospital(s) at risk",
            f"{d['road_disruptions']:+d} road disruptions", f"{d['population_at_risk']:+,} people at high risk",
        ],
    }
