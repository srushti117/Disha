"""OpenStreetMap via Overpass: road graph (intersection-to-intersection edges with real geometry), facilities, places."""
from __future__ import annotations

import json
from collections import Counter

import networkx as nx
import requests

from ..engines.geo import haversine_m
from .net import LiveDataError, UA, cache_dir, cache_key

MIRRORS = ["https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
ROAD_CLASSES = {"motorway": "primary", "trunk": "primary", "primary": "primary", "motorway_link": "primary", "trunk_link": "primary", "primary_link": "primary",
                "secondary": "secondary", "secondary_link": "secondary", "tertiary": "secondary", "tertiary_link": "secondary",
                "unclassified": "local", "residential": "local", "living_street": "local"}
MAX_EDGES = 16000


def overpass(query: str, cache_parts) -> dict:
    p = cache_dir() / f"osm_{cache_key(query, cache_parts)}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf8"))
    import time
    last = None
    for rnd in range(4):
        for url in MIRRORS:
            try:
                r = requests.post(url, data={"data": query}, timeout=150, headers=UA)
                if r.status_code == 200 and r.text.lstrip().startswith("{"):
                    j = r.json()
                    p.write_text(json.dumps(j), encoding="utf8")
                    return j
                last = f"{url}: HTTP {r.status_code}"
            except Exception as e:
                last = f"{url}: {type(e).__name__}"
        time.sleep(8 * (rnd + 1))
    raise LiveDataError(f"Overpass unavailable ({last})")


def fetch_roads(bbox) -> dict:
    w, s, e, n = bbox
    classes = "|".join(ROAD_CLASSES)
    q = f'[out:json][timeout:90];(way["highway"~"^({classes})$"]({s},{w},{n},{e}););out body geom;'
    return overpass(q, ("roads", [round(x, 4) for x in bbox]))


def fetch_features(bbox) -> dict:
    w, s, e, n = bbox
    b = f"({s},{w},{n},{e})"
    q = (
        f'[out:json][timeout:90];('
        f'nwr["amenity"~"^(hospital|clinic|doctors|school|college|fire_station|police|community_centre|shelter)$"]{b};'
        f'nwr["healthcare"="hospital"]{b};nwr["power"~"^(substation|plant)$"]{b};'
        f'nwr["man_made"~"^(water_works|water_tower|wastewater_plant|mast|tower)$"]{b};'
        f'node["place"~"^(city|town|village|hamlet|suburb|neighbourhood)$"]{b};);out center tags;'
    )
    return overpass(q, ("features", [round(x, 4) for x in bbox]))


def _bridge(tags: dict) -> bool:
    return tags.get("bridge") in ("yes", "viaduct", "movable", "cantilever", "suspension", "aqueduct") and tags.get("man_made") != "culvert"


def build_road_graph(osm: dict) -> tuple[dict[int, tuple[float, float]], list[dict]]:
    """Split ways at intersections/endpoints. Returns (nodes{id:(lat,lon)}, edges with real polyline geometry)."""
    ways = [w for w in osm.get("elements", []) if w.get("type") == "way" and w.get("geometry") and w.get("nodes")]
    use, cnt = ways, Counter()
    for lim in ({"primary", "secondary", "local"}, {"primary", "secondary"}):
        use = [w for w in ways if ROAD_CLASSES.get(w["tags"].get("highway"), "local") in lim]
        cnt = Counter()
        for w in use:
            cnt.update(set(w["nodes"]))
        n_edges = sum(1 + sum(1 for nid in w["nodes"][1:-1] if cnt[nid] > 1) for w in use)
        if n_edges <= MAX_EDGES:
            break
    coords: dict[int, tuple[float, float]] = {}
    edges: list[dict] = []
    for w in use:
        tags = w["tags"]
        cls = ROAD_CLASSES.get(tags.get("highway"), "local")
        nodes, geom = w["nodes"], [(g["lat"], g["lon"]) for g in w["geometry"]]
        if len(nodes) != len(geom):
            continue
        for nid, g in zip(nodes, geom):
            coords[nid] = g
        cut = [0] + [i for i in range(1, len(nodes) - 1) if cnt[nodes[i]] > 1] + [len(nodes) - 1]
        for a, b in zip(cut[:-1], cut[1:]):
            seg = geom[a : b + 1]
            length = sum(haversine_m(seg[i][0], seg[i][1], seg[i + 1][0], seg[i + 1][1]) for i in range(len(seg) - 1))
            if length < 1 or nodes[a] == nodes[b]:
                continue
            nm = tags.get("name") or tags.get("ref") or f"Unnamed {tags.get('highway', 'road').replace('_', ' ')}"
            edges.append({"u": nodes[a], "v": nodes[b], "class": cls, "is_bridge": _bridge(tags), "length_m": length, "name": nm, "geometry": seg, "osm_way": w["id"]})
    G = nx.Graph()
    for e in edges:
        G.add_edge(e["u"], e["v"])
    if not G.number_of_nodes():
        raise LiveDataError("No OpenStreetMap roads found in this area")
    keep = max(nx.connected_components(G), key=len)
    edges = [e for e in edges if e["u"] in keep and e["v"] in keep]
    used = sorted({e["u"] for e in edges} | {e["v"] for e in edges})
    remap = {old: i for i, old in enumerate(used)}
    nodes_out = {remap[o]: coords[o] for o in used}
    for e in edges:
        e["u"], e["v"] = remap[e["u"]], remap[e["v"]]
    return nodes_out, edges


FACILITY_RULES = [
    ("hospital", lambda t: t.get("amenity") == "hospital" or t.get("healthcare") == "hospital"),
    ("hospital", lambda t: t.get("amenity") in ("clinic", "doctors") and t.get("emergency") == "yes"),
    ("school", lambda t: t.get("amenity") in ("school", "college")),
    ("power", lambda t: t.get("power") in ("substation", "plant")),
    ("water", lambda t: t.get("man_made") in ("water_works", "water_tower", "wastewater_plant")),
    ("emergency", lambda t: t.get("amenity") in ("fire_station", "police")),
    ("comm", lambda t: t.get("man_made") in ("mast", "tower") and t.get("tower:type", "communication") == "communication"),
]
SHELTER_TYPES = {"community_centre": 250, "school": 400, "college": 500, "shelter": 100}


def parse_features(osm: dict) -> dict:
    fac, shelters, places = [], [], []
    for el in osm.get("elements", []):
        tags = el.get("tags", {})
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        if tags.get("place"):
            places.append({"name": tags.get("name", tags["place"]), "lat": lat, "lon": lon, "kind": tags["place"]})
            continue
        name = tags.get("name") or tags.get("operator") or None
        for kind, rule in FACILITY_RULES:
            if rule(tags):
                beds = tags.get("beds", "")
                fac.append({"kind": kind, "name": name or f"Unnamed {kind}", "lat": lat, "lon": lon, "capacity": int(beds) if str(beds).isdigit() else None,
                            "depends_on": [], "osm_id": f"{el['type']}/{el['id']}"})
                break
        st = tags.get("amenity")
        if st in SHELTER_TYPES and (name or st != "place_of_worship"):
            shelters.append({"name": name or f"Unnamed {st.replace('_', ' ')}", "lat": lat, "lon": lon, "capacity": SHELTER_TYPES[st], "occupied": 0,
                             "osm_id": f"{el['type']}/{el['id']}", "capacity_assumed": True})
    seen: Counter = Counter()
    for f in fac:
        base = f["name"]
        seen[base] += 1
        if seen[base] > 1:
            f["name"] = f"{base} ({seen[base]})"
    subs = [f for f in fac if f["kind"] == "power"]
    for f in fac:  # ASSUMED dependency: hospital / water / comm / emergency depend on the nearest substation within 8 km
        if f["kind"] in ("hospital", "water", "comm", "emergency") and subs:
            near = min(subs, key=lambda s: haversine_m(s["lat"], s["lon"], f["lat"], f["lon"]))
            if haversine_m(near["lat"], near["lon"], f["lat"], f["lon"]) < 8000:
                f["depends_on"] = [near["name"]]
    return {"facilities": fac, "shelters": shelters[:40], "places": places}
