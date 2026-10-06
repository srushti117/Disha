"""Procedural *simulated* world generator for DEMONSTRATION scenarios.

Everything produced here is synthetic and must be labelled "DEMO / SIMULATED DATA" wherever it is shown.
It generates the inputs a real deployment would fetch (SAR/optical rasters, DEM, population, roads,
facilities, weather). The detection, impact, priority and response engines then run on these inputs for real.
Features are placed over the user's/scenario's real-world AOI but are NOT real facilities, roads or people.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
from scipy import ndimage as ndi

from ..engines.geo import GridTransform, haversine_m

VARIANTS = {
    "flood": "flood_river",
    "flood_river": "flood_river",
    "flood_urban": "flood_urban",
    "landslide": "landslide",
    "wildfire": "wildfire",
    "cyclone": "cyclone",
}

LC_VEG, LC_CROP, LC_BUILT, LC_WATER, LC_FOREST, LC_BARE = range(6)

# backscatter (VV, dB) / NDVI / NBR means per land cover
SAR_MEAN = {LC_VEG: -9.5, LC_CROP: -10.5, LC_BUILT: -3.5, LC_WATER: -22.0, LC_FOREST: -7.5, LC_BARE: -13.0}
NDVI_MEAN = {LC_VEG: 0.6, LC_CROP: 0.55, LC_BUILT: 0.15, LC_WATER: -0.25, LC_FOREST: 0.8, LC_BARE: 0.1}
NDWI_MEAN = {LC_VEG: -0.35, LC_CROP: -0.3, LC_BUILT: -0.15, LC_WATER: 0.55, LC_FOREST: -0.45, LC_BARE: -0.1}


@dataclass
class World:
    variant: str
    hazard: str
    t: GridTransform
    seed: int
    dem: np.ndarray
    slope: np.ndarray
    landcover: np.ndarray
    pre_sar: np.ndarray
    post_sar: np.ndarray
    pre_ndvi: np.ndarray
    post_ndvi: np.ndarray
    pre_ndwi: np.ndarray
    post_ndwi: np.ndarray
    pre_nbr: np.ndarray
    post_nbr: np.ndarray
    cloud_mask: np.ndarray
    quality: np.ndarray
    pop: np.ndarray
    builtup: np.ndarray
    coast_dist_m: np.ndarray
    cloud_pct: float
    hotspots: list[dict] = field(default_factory=list)
    villages: list[dict] = field(default_factory=list)
    facilities: list[dict] = field(default_factory=list)
    shelters: list[dict] = field(default_factory=list)
    resources: list[dict] = field(default_factory=list)
    bases: list[dict] = field(default_factory=list)
    road_nodes: dict[int, tuple[float, float]] = field(default_factory=dict)
    road_edges: list[dict] = field(default_factory=list)
    weather: dict = field(default_factory=dict)
    passes: list[dict] = field(default_factory=list)
    truth: np.ndarray | None = None  # generator ground truth - never used for reporting accuracy (synthetic)
    # --- LIVE (real data) additions; defaults describe the simulated world
    is_real: bool = False
    demographics_available: bool = True
    optical_available: bool = True
    rgb: np.ndarray | None = None  # Sentinel-2 true colour (real worlds only)
    provenance: dict = field(default_factory=dict)  # per-source real dataset descriptions
    resources_note: str = ""


# --------------------------------------------------------------------------- noise helpers


def fbm(shape, rng, beta=3.0, scale=1.0):
    h, w = shape
    f = np.fft.fftfreq(h)[:, None] ** 2 + np.fft.fftfreq(w)[None, :] ** 2
    f[0, 0] = 1
    spec = (rng.normal(size=shape) + 1j * rng.normal(size=shape)) / np.power(f, beta / 4)
    spec[0, 0] = 0
    x = np.real(np.fft.ifft2(spec))
    x = (x - x.mean()) / (x.std() + 1e-9)
    return (x * scale).astype(np.float32)


def speckle_db(db_mean: np.ndarray, rng, looks=5):
    lin = np.power(10.0, db_mean / 10.0)
    g = rng.gamma(looks, 1.0 / looks, size=db_mean.shape)
    return (10 * np.log10(np.maximum(lin * g, 1e-6))).astype(np.float32)


def smoothstep(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def compute_slope(dem, px_m):
    gy, gx = np.gradient(dem, px_m)
    return np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)


# --------------------------------------------------------------------------- terrain per variant


def _terrain_flood_river(t, rng, p):
    H, W = t.height, t.width
    px = t.pixel_size_m[0]
    cols = np.arange(W)
    amp = H * 0.10
    center = H * 0.5 + amp * np.sin(2 * np.pi * cols / (W * 0.8) + rng.uniform(0, 6)) + 0.4 * amp * np.sin(2 * np.pi * cols / (W * 0.33) + rng.uniform(0, 6))
    rr = np.arange(H)[:, None]
    width_px = max(2.0, 100.0 / px) * (1 + 0.4 * np.sin(2 * np.pi * cols / (W * 0.5)))
    river = np.abs(rr - center[None, :]) < width_px[None, :]
    d = ndi.distance_transform_edt(~river) * px
    relief = p.get("relief_m", 55)
    north = smoothstep(np.broadcast_to(np.arange(H)[::-1, None] / H, (H, W)), 0.62, 1.0)  # hills on the north edge
    dem = 1.2 + 5.5 * (1 - np.exp(-d / 1800.0)) + relief * north * (0.6 + 0.4 * fbm((H, W), rng, 2.6)) + fbm((H, W), rng, 3.2, 0.9)
    dem = np.maximum(dem, 0.2)
    dem[river] = 0.5
    level = p.get("flood_level_m", 4.3) + 0.7 * p.get("progress", 0)
    lowfreq = fbm((H, W), rng, 4.5, 0.6)
    inund = (dem < level + lowfreq) & ~river
    lab, _ = ndi.label(ndi.binary_dilation(river | inund, iterations=1))
    riv_lab = np.unique(lab[river])
    riv_lab = riv_lab[riv_lab > 0]
    truth = inund & np.isin(lab, riv_lab)
    depth = np.where(truth, np.clip(level + lowfreq - dem, 0, None), 0)
    return dict(dem=dem.astype(np.float32), water=river, truth=truth, depth=depth, aux={"river": river})


def _terrain_flood_urban(t, rng, p):
    H, W = t.height, t.width
    base = fbm((H, W), rng, 3.6, 0.8) + 0.4 * fbm((H, W), rng, 2.0, 1.0)
    dem = 6 + 1.5 * base
    yy, xx = np.mgrid[0:H, 0:W]
    lake = ((yy - H * 0.22) ** 2 / (H * 0.07) ** 2 + (xx - W * 0.72) ** 2 / (W * 0.1) ** 2) < 1
    canal = (np.abs(yy - (H * 0.55 + 18 * np.sin(xx / W * 8))) < max(1.5, 40 / t.pixel_size_m[0]))
    water = lake | canal
    dem[water] = 3.0
    low = dem < np.percentile(dem[~water], p.get("pluvial_pct", 26) + 4 * p.get("progress", 0))
    truth = low & ~water
    truth = remove_small_np(truth, 20)
    depth = np.where(truth, np.clip(np.percentile(dem[~water], p.get("pluvial_pct", 26) + 4 * p.get("progress", 0)) - dem, 0, None), 0)
    return dict(dem=dem.astype(np.float32), water=water, truth=truth, depth=depth, aux={})


def _terrain_landslide(t, rng, p):
    H, W = t.height, t.width
    px = t.pixel_size_m[0]
    base = fbm((H, W), rng, 3.4)
    yy = np.arange(H)[:, None] / H
    xx = np.arange(W)[None, :] / W
    valley_c = 0.5 + 0.12 * np.sin(yy * 9) + 0.04 * fbm((H, W), rng, 3.0)[:, :1]
    dv = np.abs(xx - valley_c)
    dem = 700 + p.get("relief_m", 650) * (0.55 * smoothstep(dv, 0.0, 0.45) + 0.45 * (base - base.min()) / (base.max() - base.min() + 1e-9))
    dem = ndi.gaussian_filter(dem, 1.2)
    stream = (dv * W * px) < 35
    dem[stream] -= 12
    slope = compute_slope(dem, px)
    # scar source: steep slope above the valley floor settlement, found from the DEM itself
    steep = (slope > 22) & (slope < 36) & (dv > 0.05) & (dv < 0.22) & (yy > 0.35) & (yy < 0.75)
    noise = fbm((H, W), rng, 2.4)
    seeds = steep & (noise > np.percentile(noise[steep], 80)) if steep.any() else steep
    scar = ndi.binary_dilation(seeds, iterations=3) & (slope > 18) & (slope < 38)
    scar = remove_small_np(scar, 10)
    # debris path: steepest descent from scar centroid
    truth = scar.copy()
    if scar.any():
        r0, c0 = [int(v) for v in ndi.center_of_mass(scar)]
        path = []
        r, c = r0, c0
        for _ in range(int(2500 / px) * 3):
            path.append((r, c))
            nb = [(r + dr, c + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if (dr or dc)]
            nb = [(a, b) for a, b in nb if 0 <= a < H and 0 <= b < W]
            nxt = min(nb, key=lambda q: dem[q])
            if dem[nxt] >= dem[r, c]:
                break
            r, c = nxt
        deb = np.zeros((H, W), bool)
        for r, c in path:
            deb[r, c] = True
        deb = ndi.binary_dilation(deb, iterations=max(3, int(130 / px))) & (slope < 30)
        truth |= deb
    path_end = None
    if scar.any() and path:
        tail = path[len(path) // 2:]
        path_end = min(tail, key=lambda q: slope[q])
    return dict(dem=dem.astype(np.float32), water=stream, truth=truth, depth=None, aux={"scar": scar, "valley": dv, "stream": stream, "path_end": path_end})


def _terrain_wildfire(t, rng, p):
    H, W = t.height, t.width
    px = t.pixel_size_m[0]
    dem = 1400 + p.get("relief_m", 420) * (fbm((H, W), rng, 3.2) * 0.5 + 0.5)
    dem = ndi.gaussian_filter(dem, 1.0)
    yy, xx = np.mgrid[0:H, 0:W]
    ang = math.radians(p.get("wind_deg", 35))
    u = (xx - W * 0.4) * math.cos(ang) + (yy - H * 0.55) * math.sin(ang)
    v = -(xx - W * 0.4) * math.sin(ang) + (yy - H * 0.55) * math.cos(ang)
    env = np.exp(-(u ** 2 / (2 * (W * 0.30) ** 2) + v ** 2 / (2 * (H * 0.10) ** 2)))
    ragged = env + 0.25 * fbm((H, W), rng, 3.0)
    truth = ragged > (0.42 - 0.05 * p.get("progress", 0))
    truth = remove_small_np(truth, 30)
    stream = np.zeros((H, W), bool)
    return dict(dem=dem.astype(np.float32), water=stream, truth=truth, depth=None, aux={"u": u, "v": v})


def _terrain_cyclone(t, rng, p):
    H, W = t.height, t.width
    px = t.pixel_size_m[0]
    yy, xx = np.mgrid[0:H, 0:W]
    shore = H * 0.80 + 10 * np.sin(xx / W * 7) + 6 * fbm((H, W), rng, 3.0)[0:1, :]
    sea = yy > shore
    dist_coast = ndi.distance_transform_edt(~sea) * px
    dem = np.clip(0.8 + dist_coast / 700.0, 0, 40) + fbm((H, W), rng, 3.2, 0.6)
    dem = np.maximum(dem, 0.1)
    dem[sea] = 0
    surge = (dem < 4.0) & ~sea & (dist_coast < (p.get("surge_km", 3.6) + 0.5 * p.get("progress", 0)) * 1000)
    swath_c = H * 0.2 + W * 0.25 - 0.55 * xx
    swath = np.abs(yy - swath_c) < H * 0.20
    truth = (swath | surge) & ~sea
    return dict(dem=dem.astype(np.float32), water=sea, truth=truth, depth=None, aux={"surge": surge, "swath": swath, "sea": sea, "dist_coast": dist_coast})


def remove_small_np(mask, min_px):
    lab, n = ndi.label(mask)
    if n == 0:
        return mask
    sizes = ndi.sum(mask, lab, index=np.arange(1, n + 1))
    keep = np.zeros(n + 1, bool)
    keep[1:] = sizes >= min_px
    return keep[lab]


# --------------------------------------------------------------------------- settlements, roads, facilities


def _place_villages(t, rng, terr, variant, n, pop_total):
    H, W = t.height, t.width
    px = t.pixel_size_m[0]
    dem, water = terr["dem"], terr["water"]
    slope = compute_slope(dem, px)
    ok = (~water) & (slope < (14 if variant == "landslide" else 7))
    margin = int(0.06 * min(H, W))
    ok[:margin] = ok[-margin:] = False
    ok[:, :margin] = ok[:, -margin:] = False
    weight = np.ones((H, W), float)
    if variant == "flood_river":
        d = ndi.distance_transform_edt(~water) * px
        weight = np.exp(-((d - 900) / 1200.0) ** 2) + 0.15
    elif variant == "landslide":
        dv = terr["aux"]["valley"]
        weight = np.exp(-(dv / 0.07) ** 2) + 0.05
    elif variant == "cyclone":
        weight = np.exp(-((terr["aux"]["dist_coast"] - 1500) / 2500.0) ** 2) + 0.1
    weight = weight * ok
    flat = weight.ravel() / weight.sum()
    vill = []
    min_sep = 14
    tries = 0
    while len(vill) < n and tries < 4000:
        tries += 1
        i = rng.choice(flat.size, p=flat)
        r, c = divmod(i, W)
        if all((r - v["r"]) ** 2 + (c - v["c"]) ** 2 > min_sep ** 2 for v in vill):
            vill.append({"r": r, "c": c})
    sizes = rng.lognormal(0.0, 0.7, size=len(vill))
    sizes = sizes / sizes.sum()
    for k, v in enumerate(vill):
        v["pop"] = float(sizes[k] * pop_total * 0.85)
        v["sigma_px"] = float(np.clip((180 + 650 * math.sqrt(sizes[k])) / px, 3.0, 40.0))
        v["name"] = f"Demo Settlement {k + 1:02d}"
        v["lat"], v["lon"] = (float(x) for x in (t.rc_to_lonlat(v["r"], v["c"])[1], t.rc_to_lonlat(v["r"], v["c"])[0]))
    return vill, slope, ok


def _population_raster(t, vill, ok, pop_total, rng):
    H, W = t.height, t.width
    yy, xx = np.mgrid[0:H, 0:W]
    dens = np.zeros((H, W), float)
    for v in vill:
        s = v["sigma_px"]
        r0, r1 = max(0, int(v["r"] - 4 * s)), min(H, int(v["r"] + 4 * s) + 1)
        c0, c1 = max(0, int(v["c"] - 4 * s)), min(W, int(v["c"] + 4 * s) + 1)
        g = np.exp(-(((yy[r0:r1, c0:c1] - v["r"]) ** 2 + (xx[r0:r1, c0:c1] - v["c"]) ** 2) / (2 * s * s)))
        dens[r0:r1, c0:c1] += v["pop"] * g / (2 * np.pi * s * s)
    dens += ok * 0.0006 * pop_total / max(ok.sum(), 1)  # sparse rural background
    dens *= (0.7 + 0.3 * (fbm((H, W), rng, 2.0) * 0.5 + 0.5))
    dens = np.where(ok, dens, 0)
    dens = dens * (pop_total / max(dens.sum(), 1e-9))
    return dens.astype(np.float32)


def _build_roads(t, rng, world_dem, water, vill, variant, terr):
    W_m = (t.east - t.west) * 111_320 * math.cos(math.radians((t.south + t.north) / 2))
    H_m = (t.north - t.south) * 110_574
    sp = 1300.0 if variant != "flood_urban" else 700.0
    nx_, ny_ = max(4, int(W_m / sp) + 1), max(4, int(H_m / sp) + 1)
    nodes: dict[int, tuple[float, float]] = {}
    grid_id = {}
    for j in range(ny_):
        for i in range(nx_):
            lon = t.west + (i + 0.5 + rng.uniform(-0.2, 0.2)) / nx_ * (t.east - t.west)
            lat = t.south + (j + 0.5 + rng.uniform(-0.2, 0.2)) / ny_ * (t.north - t.south)
            k = len(nodes)
            nodes[k] = (lat, lon)
            grid_id[(i, j)] = k
    G = nx.Graph()
    G.add_nodes_from(nodes)

    def crosses_water(a, b):
        ts = np.linspace(0, 1, 40)
        lat = nodes[a][0] + (nodes[b][0] - nodes[a][0]) * ts
        lon = nodes[a][1] + (nodes[b][1] - nodes[a][1]) * ts
        vals = t.sample(water.astype(float), lon, lat, 0.0)
        return float(vals.mean())

    river_cross_cols = set()
    if variant == "flood_river":
        river_cross_cols = set(rng.choice(np.arange(1, nx_ - 1), size=min(3, nx_ - 2), replace=False).tolist())
    edges = []
    for (i, j), a in grid_id.items():
        for di, dj in ((1, 0), (0, 1)):
            b = grid_id.get((i + di, j + dj))
            if b is None or rng.random() > 0.93:
                continue
            frac = crosses_water(a, b)
            is_bridge = frac > 0.02
            if is_bridge:
                if variant == "flood_river" and dj == 1 and i in river_cross_cols:
                    pass
                elif variant == "flood_urban" and rng.random() < 0.55:
                    pass
                else:
                    continue
            cls = "primary" if (dj == 0 and j % 3 == 1) or (dj == 1 and i % 4 == 2) else ("secondary" if rng.random() < 0.4 else "local")
            edges.append((a, b, cls, is_bridge))
    # village connector nodes
    for v in vill:
        k = len(nodes)
        nodes[k] = (v["lat"], v["lon"])
        v["node"] = k
        near = sorted(nodes, key=lambda q: haversine_m(nodes[q][0], nodes[q][1], v["lat"], v["lon"]) if q != k else 1e12)[:3]
        for q in near[:2]:
            if crosses_water(k, q) < 0.02:
                edges.append((k, q, "local", False))
        if not any(e[0] == k or e[1] == k for e in edges):
            edges.append((k, near[0], "local", False))
    for a, b, cls, br in edges:
        G.add_edge(a, b)
    comp = max(nx.connected_components(G), key=len)
    keep = {n for n in comp}
    # drop villages whose connector is outside the main component by re-linking to nearest kept node
    out_edges = []
    for a, b, cls, br in edges:
        if a in keep and b in keep:
            L = haversine_m(*nodes[a], *nodes[b])
            out_edges.append({"u": a, "v": b, "class": cls, "is_bridge": br, "length_m": L,
                              "name": f"{'Bridge' if br else cls.title()} Rd {a}-{b}"})
    used = sorted({e["u"] for e in out_edges} | {e["v"] for e in out_edges})
    remap = {old: new for new, old in enumerate(used)}
    node_out = {remap[o]: nodes[o] for o in used}
    for e in out_edges:
        e["u"], e["v"] = remap[e["u"]], remap[e["v"]]
    for v in vill:
        v["node"] = remap.get(v.get("node"), None)
    return node_out, out_edges


def _make_facilities(t, rng, vill, terr, variant, dem, flooded_truth, builtup):
    fac, shelters = [], []
    order = sorted(vill, key=lambda v: -v["pop"])
    hit = (lambda v: bool(flooded_truth[int(v["r"]), int(v["c"])]))

    def mk(kind, name, v, cap=None, jitter=250, **kw):
        dlat, dlon = rng.normal(0, jitter / 111_000, 2)
        f = {"kind": kind, "name": name, "lat": v["lat"] + dlat, "lon": v["lon"] + dlon, "capacity": cap, "depends_on": []}
        f.update(kw)
        fac.append(f)
        return f

    hosp_src = []
    hit_v = [v for v in order if hit(v)]
    if hit_v:
        hosp_src.append(hit_v[0])  # at least one hospital sits in the affected area (cascade story)
    for v in order:
        if len(hosp_src) >= 3:
            break
        if v not in hosp_src:
            hosp_src.append(v)
    for k, v in enumerate(hosp_src):
        mk("hospital", f"Demo {'District Hospital' if k == 0 else 'Primary Health Centre'} {k + 1}", v, cap=int(rng.integers(60, 240)))
    for k, v in enumerate(order[:9]):
        mk("school", f"Demo School {k + 1:02d}", v, cap=int(rng.integers(300, 900)), jitter=350)
    subs = []
    for k, v in enumerate(order[:3]):
        subs.append(mk("power", f"Demo Power Substation {k + 1}", v, jitter=600))
    for k, v in enumerate(order[1:3]):
        mk("water", f"Demo Water Treatment {k + 1}", v, jitter=500)
    for k, v in enumerate(order[2:4]):
        mk("emergency", f"Demo Fire & Emergency Station {k + 1}", v, jitter=300)
    for k, v in enumerate(order[:3]):
        mk("comm", f"Demo Telecom Tower {k + 1}", v, jitter=700)
    for f in fac:
        if f["kind"] in ("hospital", "water", "comm", "emergency"):
            near = min(subs, key=lambda s: haversine_m(s["lat"], s["lon"], f["lat"], f["lon"]))
            f["depends_on"] = [near["name"]]
    # shelters: prefer higher ground; one deliberately low-lying so the planner can flag it
    sh_cands = sorted(vill, key=lambda v: -dem[int(v["r"]), int(v["c"])] * (1 if variant != "flood_urban" else -1))
    names = ["Community Hall", "Higher-Secondary School Shelter", "Relief Camp", "Temple Hall Shelter", "Sports Complex Shelter", "Panchayat Shelter"]
    for k, v in enumerate(sh_cands[:5]):
        dlat, dlon = rng.normal(0, 300 / 111_000, 2)
        shelters.append({"name": f"Demo {names[k % len(names)]} {k + 1}", "lat": v["lat"] + dlat, "lon": v["lon"] + dlon,
                         "capacity": int(rng.integers(350, 900)), "occupied": int(rng.integers(0, 80))})
    if hit_v:
        v = hit_v[-1]
        shelters.append({"name": "Demo Low-lying Relief Camp", "lat": v["lat"], "lon": v["lon"], "capacity": 500, "occupied": 0})
    return fac, shelters


def _bases_and_resources(t, rng, node_pos, flooded_truth, spec):
    # two response bases on the safest edge nodes (not in truth hazard)
    cand = []
    for k, (lat, lon) in node_pos.items():
        r, c = t.lonlat_to_rc(lon, lat)
        r, c = int(np.clip(r, 0, t.height - 1)), int(np.clip(c, 0, t.width - 1))
        if not flooded_truth[r, c]:
            cand.append((k, lat, lon))
    cand.sort(key=lambda x: (-x[1], x[2]))  # north-west
    b1 = cand[0]
    b2 = max(cand, key=lambda x: haversine_m(x[1], x[2], b1[1], b1[2]))
    bases = [{"name": "Demo Response Base Alpha", "lat": b1[1], "lon": b1[2], "node": b1[0]},
             {"name": "Demo Response Base Bravo", "lat": b2[1], "lon": b2[2], "node": b2[0]}]
    counts = spec.get("resources", {"rescue_team": 12, "ambulance": 6, "boat": 4, "medical_team": 4, "drone": 3, "relief_vehicle": 6})
    speeds = {"rescue_team": 35, "ambulance": 45, "boat": 18, "medical_team": 40, "drone": 55, "relief_vehicle": 30}
    label = {"rescue_team": "Rescue Team", "ambulance": "Ambulance", "boat": "Boat", "medical_team": "Medical Team", "drone": "Drone", "relief_vehicle": "Relief Vehicle"}
    res = []
    for kind, n in counts.items():
        for i in range(n):
            b = bases[i % 2]
            res.append({"kind": kind, "name": f"{label[kind]} {i + 1:02d}", "lat": b["lat"] + rng.normal(0, 0.0004), "lon": b["lon"] + rng.normal(0, 0.0004),
                        "speed_kmh": speeds[kind], "base": b["name"]})
    return bases, res


# --------------------------------------------------------------------------- main builder


def build_world(hazard: str, bounds: tuple, seed: int = 7, params: dict | None = None, variant: str | None = None,
                target_px_m: float = 30.0) -> World:
    p = dict(params or {})
    variant = variant or VARIANTS.get(hazard, "flood_river")
    rng = np.random.default_rng(seed)
    t = GridTransform.for_bounds(bounds, target_px_m=target_px_m)
    H, W = t.height, t.width
    px = t.pixel_size_m[0]
    terr = {"flood_river": _terrain_flood_river, "flood_urban": _terrain_flood_urban, "landslide": _terrain_landslide,
            "wildfire": _terrain_wildfire, "cyclone": _terrain_cyclone}[variant](t, rng, p)
    dem, water, truth = terr["dem"], terr["water"], terr["truth"]

    pop_total = p.get("pop_total", 90_000)
    vill, slope, ok = _place_villages(t, rng, terr, variant, p.get("n_villages", 14), pop_total)
    pop = _population_raster(t, vill, ok, pop_total, rng)
    pix_area_km2 = (px ** 2) / 1e6
    built_thr = 1800.0 * pix_area_km2 if variant != "flood_urban" else 900.0 * pix_area_km2
    builtup = (ndi.gaussian_filter(pop, 1.0) > built_thr) & ~water
    if variant == "flood_urban":
        builtup |= (~water) & (fbm((H, W), rng, 2.4) > -0.45)
        builtup &= ~water

    # land cover
    crop_field = fbm((H, W), rng, 2.6)
    lc = np.where(crop_field > 0.1, LC_CROP, LC_VEG).astype(np.int8)
    forest_amount = {"landslide": -0.2, "wildfire": -0.5, "flood_river": 0.55, "cyclone": 0.5, "flood_urban": 2.0}[variant]
    forest_field = fbm((H, W), rng, 2.8)
    lc[forest_field > forest_amount + 0.6] = LC_FOREST
    if variant in ("landslide", "wildfire"):
        lc[(dem > np.percentile(dem, 35))] = LC_FOREST
    lc[builtup] = LC_BUILT
    lc[water] = LC_WATER
    bare_patch = (slope > 38) if variant == "landslide" else np.zeros((H, W), bool)
    lc[bare_patch & ~builtup] = LC_BARE

    if variant == "landslide" and terr["aux"].get("path_end") and vill:
        pr, pc = terr["aux"]["path_end"]
        near = min(vill, key=lambda v: (v["r"] - pr) ** 2 + (v["c"] - pc) ** 2)
        near["r"], near["c"] = int(np.clip(pr, 2, H - 3)), int(np.clip(pc, 2, W - 3))  # settlement in the run-out path (scenario design)
        lon_, lat_ = t.rc_to_lonlat(near["r"], near["c"])
        near["lat"], near["lon"] = float(lat_), float(lon_)
        near["pop"] *= 1.5
        near["sigma_px"] = max(near["sigma_px"], 9.0)
        yy_, xx_ = np.mgrid[0:H, 0:W]
        ok = ok | (((yy_ - near["r"]) ** 2 + (xx_ - near["c"]) ** 2) < 14 ** 2) & ~water
        pop = _population_raster(t, vill, ok, pop_total, rng)
        builtup = (ndi.gaussian_filter(pop, 1.0) > built_thr) & ~water

    # ---- pre-event signal means
    sar_mean = np.vectorize(SAR_MEAN.get)(lc).astype(np.float32) if False else np.choose(lc, [SAR_MEAN[i] for i in range(6)]).astype(np.float32)
    tex = ndi.gaussian_filter(rng.normal(0, 1, (H, W)), 2) * 2.2
    sar_mean = sar_mean + tex
    shadow = slope > 40
    sar_mean[shadow & ~water] = -19.0
    quality = ~shadow
    ndvi_pre = np.choose(lc, [NDVI_MEAN[i] for i in range(6)]).astype(np.float32) + fbm((H, W), rng, 1.8, 0.04)
    ndwi_pre = np.choose(lc, [NDWI_MEAN[i] for i in range(6)]).astype(np.float32) + fbm((H, W), rng, 1.8, 0.05)
    nbr_pre = np.where(np.isin(lc, [LC_FOREST, LC_VEG, LC_CROP]), ndvi_pre * 0.92 - 0.02, ndvi_pre * 0.5 - 0.1).astype(np.float32)

    # ---- post-event
    sar_post = sar_mean.copy()
    ndvi_post = ndvi_pre.copy()
    ndwi_post = ndwi_pre.copy()
    nbr_post = nbr_pre.copy()
    # seasonal / agricultural false change (not hazard related)
    harvest = (fbm((H, W), rng, 2.4) > 0.9) & (lc == LC_CROP)
    sar_post[harvest] += rng.uniform(-5.0, -2.5)
    ndvi_post[harvest] -= 0.18
    ndvi_post += fbm((H, W), rng, 2.0, 0.03)
    sar_post += float(rng.normal(0, 0.25))  # radiometric difference between acquisitions

    hotspots: list[dict] = []
    if variant in ("flood_river", "flood_urban"):
        fl = truth
        deepw = np.where(builtup, 2.8, np.where(lc == LC_FOREST, 7.0, -19.0 - sar_mean * 0)) if False else None
        post_val = np.where(builtup, sar_mean + 2.8, np.where(lc == LC_FOREST, sar_mean - 6.5, -19.0 + 0.0 * sar_mean))
        if variant == "flood_urban":  # some streets still drop (smooth asphalt ponding)
            street = fbm((H, W), rng, 2.0) > 0.5
            post_val = np.where(builtup & street, -18.0, post_val)
        sar_post = np.where(fl, post_val + tex * 0.2, sar_post)
        ndwi_post = np.where(fl & ~builtup, 0.38 + fbm((H, W), rng, 2.0, 0.06), np.where(fl, 0.02, ndwi_post))
        ndvi_post = np.where(fl, np.minimum(ndvi_post, 0.05), ndvi_post)
    elif variant == "landslide":
        scar = terr["aux"]["scar"]
        deb = truth & ~scar
        sar_post = np.where(scar, sar_mean - 5.0, np.where(deb, sar_mean + 5.5, sar_post))
        ndvi_post = np.where(scar, 0.12, np.where(deb, 0.18, ndvi_post))
    elif variant == "wildfire":
        burn = truth
        u, v = terr["aux"]["u"], terr["aux"]["v"]
        sev = np.clip(0.5 + 0.5 * fbm((H, W), rng, 2.6), 0.2, 1.0) * burn
        nbr_post = np.where(burn, nbr_pre - (0.25 + 0.95 * sev), nbr_post)
        ndvi_post = np.where(burn, ndvi_pre - (0.2 + 0.5 * sev), ndvi_post)
        sar_post = np.where(burn, sar_mean - (1.5 + 2.5 * sev), sar_post)
        front = burn & ~ndi.binary_erosion(burn, iterations=3) & (u > np.percentile(u[burn], 55))
        fr, fc = np.nonzero(front)
        if len(fr):
            pick = rng.choice(len(fr), size=min(34, len(fr)), replace=False)
            for i in pick:
                lon, lat = t.rc_to_lonlat(fr[i], fc[i])
                hotspots.append({"lat": float(lat), "lon": float(lon), "frp": float(rng.uniform(6, 85)),
                                 "confidence": str(rng.choice(["nominal", "high", "high"]))})
    elif variant == "cyclone":
        sw, sg = terr["aux"]["swath"], terr["aux"]["surge"]
        vegloss = np.clip(0.1 + 0.4 * (fbm((H, W), rng, 2.4) * 0.5 + 0.5), 0, 0.6)
        dmg = sw & ~water
        ndvi_post = np.where(dmg & (lc != LC_BUILT), ndvi_pre - vegloss, ndvi_post)
        sar_post = np.where(dmg & (lc != LC_BUILT), sar_mean + rng.choice([-1, 1]) * (2.0 + 2.0 * (fbm((H, W), rng, 2.5) > 0)), sar_post)
        roof = dmg & (lc == LC_BUILT) & (fbm((H, W), rng, 1.6) > -0.2)
        sar_post = np.where(roof, sar_mean - 4.5, sar_post)
        sar_post = np.where(sg, -19.0, sar_post)
        ndwi_post = np.where(sg, 0.3, ndwi_post)

    # cloud on post-event optical
    cloud_pct = float(p.get("cloud_pct", 80.0))
    cf = fbm((H, W), rng, 3.4)
    cloud = cf > np.percentile(cf, 100 - cloud_pct) if cloud_pct > 0 else np.zeros((H, W), bool)
    cloud_actual = float(cloud.mean() * 100)
    for a in (ndvi_post, ndwi_post, nbr_post):
        a[cloud] = np.nan

    pre_sar = speckle_db(sar_mean, rng)
    post_sar = speckle_db(sar_post, rng)
    pre_sar[~quality] = np.nan if False else pre_sar[~quality]

    coast = terr["aux"].get("dist_coast", np.full((H, W), 1e9, np.float32))
    node_pos, edges = _build_roads(t, rng, dem, water, vill, variant, terr)
    fac, shelters = _make_facilities(t, rng, vill, terr, variant, dem, truth, builtup)
    bases, resources = _bases_and_resources(t, rng, node_pos, truth, p)

    weather = p.get("weather") or {
        "rainfall_mm": {"6": 38, "12": 66, "24": 112}, "river_level_trend_m_per_h": 0.11, "wind_kmh": 22,
        "source": "DEMO / SIMULATED forecast", "note": "Not a live weather feed.",
    }
    return World(
        variant=variant, hazard=hazard, t=t, seed=seed, dem=dem, slope=slope, landcover=lc,
        pre_sar=pre_sar, post_sar=post_sar, pre_ndvi=ndvi_pre.astype(np.float32), post_ndvi=ndvi_post.astype(np.float32),
        pre_ndwi=ndwi_pre.astype(np.float32), post_ndwi=ndwi_post.astype(np.float32),
        pre_nbr=nbr_pre.astype(np.float32), post_nbr=nbr_post.astype(np.float32),
        cloud_mask=cloud, quality=quality, pop=pop, builtup=builtup, coast_dist_m=coast.astype(np.float32),
        cloud_pct=cloud_actual, hotspots=hotspots, villages=vill, facilities=fac, shelters=shelters,
        resources=resources, bases=bases, road_nodes=node_pos, road_edges=edges, weather=weather, truth=truth,
    )
