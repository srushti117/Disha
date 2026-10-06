"""Cascade impact engine: dependency chains (power -> hospital -> EMS, bridge -> roads -> isolation -> rescue delay)."""
from __future__ import annotations

from .geo import haversine_m


def facility_cascades(facilities: list[dict], cell_hazard: dict[str, float], cell_access_loss: dict[str, float],
                      bridge_deps: dict[str, set[int]], node_cell: dict[int, str]) -> dict:
    """facilities: dicts with name, kind, h3_index, depends_on(list of names).
    cell_hazard: h3 -> hazard exposure 0..1 (max of own / 0.6*neighbour). Returns per-facility risk and per-cell cascades."""
    by_name = {f["name"]: f for f in facilities}
    direct = {}
    for f in facilities:
        h = cell_hazard.get(f.get("h3_index"), 0.0)
        direct[f["name"]] = (h, "inside or adjacent to affected area" if h > 0.15 else "")
    fac_out: dict[str, dict] = {}
    for f in facilities:
        h, why = direct[f["name"]]
        risk, reasons, chain = h, [], []
        if why:
            reasons.append(f"{f['name']} is {why}")
        for up in f.get("depends_on", []):
            u = by_name.get(up)
            if not u:
                continue
            uh = direct[u["name"]][0]
            if uh > 0.25:
                inherited = 0.55 + 0.4 * uh
                if inherited > risk:
                    risk = inherited
                reasons.append(f"Depends on {up}, which is exposed (hazard exposure {uh:.0%})")
                chain.append(up)
        loss = cell_access_loss.get(f.get("h3_index"), 0.0)
        if f["kind"] in ("hospital", "emergency") and loss >= 0.5:
            risk = max(risk, 0.5 + 0.3 * loss)
            reasons.append("Road access to the facility is disrupted - emergency medical service delay")
            chain.append("road access")
        status = "impaired" if risk >= 0.7 else "at_risk" if risk >= 0.25 else "operational"
        fac_out[f["name"]] = {"risk": round(min(risk, 1.0), 3), "status": status, "reason": "; ".join(reasons), "chain": chain}

    cell_out: dict[str, dict] = {}

    def bump(cell, risk, reason, dep):
        c = cell_out.setdefault(cell, {"risk": 0.0, "reasons": [], "deps": []})
        c["risk"] = max(c["risk"], risk)
        if reason not in c["reasons"]:
            c["reasons"].append(reason)
        if dep and dep not in c["deps"]:
            c["deps"].append(dep)

    for f in facilities:
        r = fac_out[f["name"]]
        if r["risk"] >= 0.25 and f.get("h3_index"):
            kind = f["kind"].replace("_", " ")
            dep = f"{kind}: {f['name']}"
            reason = (r["reason"] or f"{f['name']} at risk")
            if f["kind"] == "power":
                reason += " -> downstream hospital / water / communications at risk"
            bump(f["h3_index"], r["risk"], reason, dep)
    for bname, nodes in bridge_deps.items():
        cells = {node_cell[n] for n in nodes if n in node_cell}
        for c in cells:
            bump(c, 0.75, f"{bname} blocked -> road network cut -> village isolation -> rescue delay", f"bridge: {bname}")
    return {"facilities": fac_out, "cells": {c: {"cascade_risk": round(v["risk"], 3), "cascade_reason": " | ".join(v["reasons"][:3]),
                                                  "affected_dependencies": v["deps"][:6]} for c, v in cell_out.items()}}
