"""Road network intelligence: hazard intersection, status classification, criticality, isolation analysis."""
from __future__ import annotations

import math

import h3
import networkx as nx
import numpy as np
from scipy import ndimage as ndi

from .geo import GridTransform, haversine_m

BLOCK_FRAC = 0.30
BRIDGE_BLOCK_FRAC = 0.15
PB_FRAC = 0.05


def _polyline_samples(geom: list[tuple[float, float]], step_m: float):
    """Sample points (lat, lon arrays) every ~step_m along a polyline given as [(lat, lon), ...]."""
    pts = np.asarray(geom, dtype=float)
    kx = 111_320 * math.cos(math.radians(pts[:, 0].mean()))
    seg = np.hypot((pts[1:, 0] - pts[:-1, 0]) * 110_574, (pts[1:, 1] - pts[:-1, 1]) * kx)
    cum = np.r_[0.0, np.cumsum(seg)]
    total = float(cum[-1])
    n = max(2, int(math.ceil(total / step_m)) + 1)
    d = np.linspace(0, total, n)
    return np.interp(d, cum, pts[:, 0]), np.interp(d, cum, pts[:, 1])


def classify_segments(edges: list[dict], nodes: dict[int, tuple[float, float]], t: GridTransform, hazard_mask: np.ndarray,
                      quality: np.ndarray | None, res: int, sample_every_m: float = 60.0) -> list[dict]:
    near = ndi.binary_dilation(hazard_mask, iterations=2)
    out = []
    G = nx.Graph()
    for e in edges:
        G.add_edge(e["u"], e["v"])
    bridges_graph = {frozenset(b) for b in nx.bridges(G)} if G.number_of_edges() else set()
    for e in edges:
        geom = e.get("geometry") or [nodes[e["u"]], nodes[e["v"]]]
        lat, lon = _polyline_samples(geom, sample_every_m)
        inside = t.sample(hazard_mask.astype(float), lon, lat, 0.0)
        adj = t.sample(near.astype(float), lon, lat, 0.0)
        if quality is not None:
            q = t.sample(quality.astype(float), lon, lat, np.nan)
            nodata = float(np.mean(~np.isfinite(q) | (q < 0.5)))
        else:
            nodata = 0.0
        frac = float(inside.mean())
        thr = BRIDGE_BLOCK_FRAC if e["is_bridge"] else BLOCK_FRAC
        if nodata > 0.5:
            status = "unknown"
        elif frac >= thr:
            status = "blocked"
        elif frac >= PB_FRAC or float(adj.mean()) >= 0.25:
            status = "potentially_blocked"
        else:
            status = "open"
        cells = sorted({h3.latlng_to_cell(float(a), float(b), res) for a, b in zip(lat, lon)})
        crit = bool(e["is_bridge"] or e["class"] == "primary" or frozenset((e["u"], e["v"])) in bridges_graph)
        out.append({**e, "status": status, "flooded_fraction": round(frac, 3), "h3_indices": cells, "is_critical": crit,
                    "coords": [[round(float(g[1]), 6), round(float(g[0]), 6)] for g in geom]})
    return out


def usable_graph(segments: list[dict], include_pb: bool = True) -> nx.Graph:
    G = nx.Graph()
    for s in segments:
        if s["status"] == "blocked":
            continue
        if s["status"] == "potentially_blocked" and not include_pb:
            continue
        G.add_edge(s["u"], s["v"])
    return G


def reachable_from(segments: list[dict], sources: list[int], include_pb: bool = True) -> set[int]:
    G = usable_graph(segments, include_pb)
    out: set[int] = set()
    for s in sources:
        if s in G:
            out |= nx.node_connected_component(G, s)
    return out


def bridge_dependents(segments: list[dict], sources: list[int]) -> dict[str, set[int]]:
    """For each blocked critical edge: nodes that would regain access if only that edge were restored."""
    base = reachable_from(segments, sources)
    deps: dict[str, set[int]] = {}
    for s in segments:
        if s["status"] != "blocked" or not (s["is_bridge"] or s["is_critical"]):
            continue
        G = usable_graph(segments)
        G.add_edge(s["u"], s["v"])
        reach = set()
        for src in sources:
            if src in G:
                reach |= nx.node_connected_component(G, src)
        extra = reach - base
        if extra:
            deps[s["name"]] = extra
    return deps


def cell_access(segments: list[dict], nodes: dict[int, tuple[float, float]], cell_ids: list[str], cell_centers: dict[str, tuple[float, float]],
                sources: list[int], max_snap_m: float = 2500.0) -> dict[str, dict]:
    """Per-cell road length stats, access loss (0..1), road status and isolation flag."""
    reach = reachable_from(segments, sources)
    stats = {c: {"len": 0.0, "blocked": 0.0, "pb": 0.0, "unknown": 0.0, "n": 0} for c in cell_ids}
    for s in segments:
        share = s["length_m"] / max(len(s["h3_indices"]), 1)
        for c in s["h3_indices"]:
            if c in stats:
                d = stats[c]
                d["len"] += share
                d["n"] += 1
                if s["status"] == "blocked":
                    d["blocked"] += share
                elif s["status"] == "potentially_blocked":
                    d["pb"] += share
                elif s["status"] == "unknown":
                    d["unknown"] += share
    out = {}
    ids = np.fromiter(nodes.keys(), dtype=int)
    arr = np.array([nodes[i] for i in ids], dtype=float)
    for c in cell_ids:
        d = stats[c]
        lat, lon = cell_centers[c]
        dist_m = np.hypot((arr[:, 0] - lat) * 110_574, (arr[:, 1] - lon) * 111_320 * math.cos(math.radians(lat)))
        k = int(np.argmin(dist_m))
        nid, dist = int(ids[k]), float(dist_m[k])
        isolated = bool(dist <= max_snap_m and nid not in reach)
        if d["len"] == 0 and dist > max_snap_m:
            out[c] = {"access_loss": 0.25, "road_status": "unknown", "isolated": False, "node": None, "road_m": 0.0}
            continue
        loss = (d["blocked"] + 0.5 * d["pb"]) / d["len"] if d["len"] else 0.0
        if isolated:
            loss = 1.0
        status = "blocked" if (isolated or (d["len"] and d["blocked"] / d["len"] >= 0.5)) else             "potentially_blocked" if (d["blocked"] > 0 or d["pb"] > 0) else             "unknown" if (d["len"] and d["unknown"] / d["len"] > 0.5) else "open"
        out[c] = {"access_loss": round(min(1.0, loss), 3), "road_status": status, "isolated": isolated, "node": nid, "road_m": round(d["len"], 1)}
    return out
