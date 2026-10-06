"""Rescue route optimiser: shortest / fastest / safest routes over the hazard-aware road graph (NetworkX)."""
from __future__ import annotations

from dataclasses import dataclass, field

import math

import networkx as nx
import numpy as np
from scipy.spatial import cKDTree

from .geo import haversine_m

SPEED_KMH = {"primary": 50.0, "secondary": 35.0, "local": 22.0}
STATUS_RISK = {"open": 0.05, "potentially_blocked": 0.6, "unknown": 0.35, "blocked": 1.0}
STATUS_SPEED_FACTOR = {"open": 1.0, "potentially_blocked": 0.5, "unknown": 0.8, "blocked": 0.0}


def build_graph(segments: list[dict], cell_severity: dict[str, float] | None = None) -> nx.Graph:
    G = nx.Graph()
    for s in segments:
        sev = 0.0
        if cell_severity and s.get("h3_indices"):
            sev = sum(cell_severity.get(c, 0.0) for c in s["h3_indices"]) / len(s["h3_indices"])
        risk = max(STATUS_RISK.get(s["status"], 0.35), 0.8 * sev)
        speed = SPEED_KMH.get(s["class"], 22.0) * (0.7 if s.get("is_bridge") else 1.0) * STATUS_SPEED_FACTOR.get(s["status"], 0.8)
        free_speed = SPEED_KMH.get(s["class"], 22.0)
        L = s["length_m"]
        G.add_edge(s["u"], s["v"], length=L, status=s["status"], risk=risk, name=s["name"], seg_id=s.get("id"),
                   time_min=(L / 1000) / speed * 60 if speed > 0 else float("inf"),
                   free_time_min=(L / 1000) / free_speed * 60, coords=s.get("coords"), u=s["u"])
    return G


_INDEX: dict[int, tuple] = {}


def _index(nodes: dict[int, tuple[float, float]]):
    key = id(nodes)
    hit = _INDEX.get(key)
    if hit is None or hit[2] != len(nodes):
        ids = np.fromiter(nodes.keys(), dtype=int)
        arr = np.array([nodes[i] for i in ids], dtype=float)
        lat0 = float(arr[:, 0].mean())
        pts = np.c_[arr[:, 0] * 110_574, arr[:, 1] * 111_320 * math.cos(math.radians(lat0))]
        if len(_INDEX) > 6:
            _INDEX.clear()
        hit = (cKDTree(pts), ids, len(nodes), lat0)
        _INDEX[key] = hit
    return hit


def nearest_node(nodes: dict[int, tuple[float, float]], lat: float, lon: float, graph: nx.Graph | None = None,
                 exclude_isolated_from: set[int] | None = None) -> tuple[int, float]:
    """Nearest road node (metres) via a cached KD-tree; optionally restricted to nodes present in `graph` / in a reachable set."""
    tree, ids, _, lat0 = _index(nodes)
    q = [lat * 110_574, lon * 111_320 * math.cos(math.radians(lat0))]
    k = 1
    while True:
        k = min(len(ids), k * 8) if k > 1 else min(len(ids), 8)
        dist, idx = tree.query(q, k=k)
        for d, i in zip(np.atleast_1d(dist), np.atleast_1d(idx)):
            nid = int(ids[i])
            if graph is not None and nid not in graph:
                continue
            if exclude_isolated_from is not None and nid not in exclude_isolated_from:
                continue
            return nid, float(d)
        if k >= len(ids):
            raise ValueError("no road nodes available")


@dataclass
class RouteResult:
    kind: str
    feasible: bool
    node_path: list[int] = field(default_factory=list)
    coords: list[list[float]] = field(default_factory=list)
    distance_km: float = 0.0
    eta_min: float = 0.0
    risk: float = 0.0
    blocked_segments: int = 0
    potentially_blocked_segments: int = 0
    notes: str = ""
    segment_names: list[str] = field(default_factory=list)

    def to_dict(self):
        return self.__dict__.copy()


def _path_metrics(G: nx.Graph, nodes, path: list[int], kind: str) -> RouteResult:
    dist = time = 0.0
    risks, blocked, pb, names, coords = [], 0, 0, [], []
    for a, b in zip(path[:-1], path[1:]):
        e = G[a][b]
        dist += e["length"]
        t = e["time_min"] if e["time_min"] != float("inf") else e["free_time_min"] * 2.5  # blocked: crossing would need clearing
        time += t
        risks.append(e["risk"] * e["length"])
        blocked += e["status"] == "blocked"
        pb += e["status"] == "potentially_blocked"
        if e["status"] in ("blocked", "potentially_blocked"):
            names.append(f'{e["name"]} ({e["status"].replace("_", " ")})')
        seq = e.get("coords")
        if seq and len(seq) >= 2:
            seq = seq if e.get("u") == a else seq[::-1]  # orient along the direction of travel
            coords.extend([list(c) for c in (seq if not coords else seq[1:])])
        else:
            la, lo = nodes[a]
            if not coords:
                coords.append([lo, la])
            la, lo = nodes[b]
            coords.append([lo, la])
    return RouteResult(kind, blocked == 0, path, coords, round(dist / 1000, 2), round(time, 1),
                       round(sum(risks) / dist, 3) if dist else 0.0, int(blocked), int(pb), segment_names=names)


def route_options(G: nx.Graph, nodes: dict[int, tuple[float, float]], origin_node: int, target_node: int) -> dict:
    """Return shortest (may be blocked), fastest and safest (blocked edges excluded) + recommendation."""
    out: dict[str, RouteResult] = {}
    if origin_node == target_node:
        r = RouteResult("shortest", True, [origin_node], [[nodes[origin_node][1], nodes[origin_node][0]]], notes="Origin is at the target access node.")
        return {"routes": {"shortest": r, "fastest": r, "safest": r}, "recommended": "safest"}
    try:
        p = nx.shortest_path(G, origin_node, target_node, weight="length")
        out["shortest"] = _path_metrics(G, nodes, p, "shortest")
    except nx.NetworkXNoPath:
        out["shortest"] = RouteResult("shortest", False, notes="No physical road connection between origin and target.")
    usable = nx.Graph(((u, v, d) for u, v, d in G.edges(data=True) if d["status"] != "blocked"))
    usable.add_nodes_from(G.nodes)
    for kind, wfun in (
        ("fastest", lambda u, v, d: d["time_min"]),
        ("safest", lambda u, v, d: d["length"] * (1 + 8 * d["risk"]) + (4000 if d["status"] == "potentially_blocked" else 0)),
    ):
        try:
            p = nx.shortest_path(usable, origin_node, target_node, weight=wfun)
            out[kind] = _path_metrics(usable, nodes, p, kind)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            out[kind] = RouteResult(kind, False, notes="No open road route - consider boat/air access or clearing the blocked segments.")
    feasible = [r for r in out.values() if r.feasible and r.node_path]
    rec = None
    if feasible:
        rec = min(feasible, key=lambda r: r.eta_min * (1 + 2.0 * r.risk) + 3.0 * r.potentially_blocked_segments + 3.0 * r.blocked_segments)
        rec_kind = rec.kind
    else:
        rec_kind = None
    return {"routes": out, "recommended": rec_kind}


def explain(routes: dict) -> str:
    out = []
    names = {"shortest": "A", "fastest": "B", "safest": "C"}
    for k, r in routes["routes"].items():
        if not r.node_path:
            out.append(f"Route {names[k]} ({k}): not available.")
            continue
        state = "BLOCKED" if r.blocked_segments else ("OPEN - " + ("LOW" if r.risk < 0.2 else "MODERATE" if r.risk < 0.45 else "HIGH") + " RISK")
        out.append(f"Route {names[k]} ({k}): {r.distance_km} km, ETA {r.eta_min:.0f} min, {state}")
    rec = routes["recommended"]
    out.append(f"Recommended: {rec.upper()} route." if rec else "Recommended: none - no fully open road route.")
    return "\n".join(out)
