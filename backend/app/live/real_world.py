"""Assemble a `World` from REAL open data (same contract as demo.world.build_world, so every downstream engine is unchanged).

Sources: Sentinel-1 RTC + Sentinel-2 L2A + Copernicus DEM GLO-30 + ESA WorldCover (Microsoft Planetary Computer, anonymous),
WorldPop 2020 (population), OpenStreetMap (roads, facilities, places), Open-Meteo (rainfall). Nothing is simulated except the
response-resource roster (no real resource feed exists) which is labelled hypothetical.
"""
from __future__ import annotations

import logging
import pickle
from datetime import datetime, timezone
from typing import Callable

import numpy as np
from scipy import ndimage as ndi

from ..demo.world import LC_BARE, LC_BUILT, LC_CROP, LC_FOREST, LC_VEG, LC_WATER, World, compute_slope
from ..engines.geo import GridTransform, haversine_m
from . import imagery, osm, population, weather
from .net import LiveDataError, cache_dir, cache_key

log = logging.getLogger("disha.live")
WC_TO_LC = {10: LC_FOREST, 20: LC_VEG, 30: LC_VEG, 40: LC_CROP, 50: LC_BUILT, 60: LC_BARE, 70: LC_BARE, 80: LC_WATER, 90: LC_WATER, 95: LC_WATER, 100: LC_VEG}
DEFAULT_ROSTER = {"rescue_team": 12, "ambulance": 6, "boat": 4, "medical_team": 4, "drone": 3, "relief_vehicle": 6}
SPEEDS = {"rescue_team": 35, "ambulance": 45, "boat": 18, "medical_team": 40, "drone": 55, "relief_vehicle": 30}
LABEL = {"rescue_team": "Rescue Team", "ambulance": "Ambulance", "boat": "Boat", "medical_team": "Medical Team", "drone": "Drone", "relief_vehicle": "Relief Vehicle"}


def _nearest_node(nodes: dict, lat: float, lon: float) -> int:
    ids = np.fromiter(nodes.keys(), int)
    arr = np.array([nodes[i] for i in ids])
    d = (arr[:, 0] - lat) ** 2 + ((arr[:, 1] - lon) * np.cos(np.radians(lat))) ** 2
    return int(ids[int(np.argmin(d))])


def build_live_world(hazard: str, bounds: tuple, pre_end, post_start, post_end, params: dict | None = None,
                     progress: Callable[[str], None] | None = None, target_px_m: float = 30.0) -> World:
    p = dict(params or {})
    say = progress or (lambda m: None)
    ck = cache_dir() / f"world_{cache_key(hazard, [round(b, 4) for b in bounds], str(pre_end), str(post_start), str(post_end), p.get('iso3'), p.get('roster'), target_px_m)}.pkl"
    if ck.exists():
        say("Loaded previously retrieved real datasets from local cache")
        return pickle.loads(ck.read_bytes())

    t = GridTransform.for_bounds(bounds, target_px_m=target_px_m)
    px = t.pixel_size_m[0]
    prov: dict = {}
    lat0, lon0 = t.center
    # ---- Sentinel-1
    say("Searching Sentinel-1 RTC scenes (same orbit track before/after)…")
    pre_it, post_it = imagery.pick_s1_pair(bounds, pre_end, post_start, post_end)
    say(f"Reading Sentinel-1 {pre_it['properties']['datetime'][:10]} (pre) and {post_it['properties']['datetime'][:10]} (post)…")
    pre_sar, post_sar = imagery.read_s1_db(pre_it, t), imagery.read_s1_db(post_it, t)
    if not (np.isfinite(pre_sar).mean() > 0.5 and np.isfinite(post_sar).mean() > 0.5):
        raise LiveDataError("Sentinel-1 scenes cover less than half of the area with valid data")
    post_dt = datetime.fromisoformat(post_it["properties"]["datetime"].replace("Z", "+00:00"))
    pre_dt = datetime.fromisoformat(pre_it["properties"]["datetime"].replace("Z", "+00:00"))
    passes = [
        {"sensor": "sentinel-1", "phase": "pre", "acquired_at": pre_dt, "cloud_cover_pct": None, "orbit": f"{pre_it['properties'].get('sat:orbit_state', '?')} rel. orbit {pre_it['properties'].get('sat:relative_orbit', '?')}",
         "polarisation": "VV (RTC gamma0)", "source": f"Microsoft Planetary Computer sentinel-1-rtc: {pre_it['id']}"},
        {"sensor": "sentinel-1", "phase": "post", "acquired_at": post_dt, "cloud_cover_pct": None, "orbit": f"{post_it['properties'].get('sat:orbit_state', '?')} rel. orbit {post_it['properties'].get('sat:relative_orbit', '?')}",
         "polarisation": "VV (RTC gamma0)", "source": f"Microsoft Planetary Computer sentinel-1-rtc: {post_it['id']}"},
    ]
    prov["satellite"] = {"name": "Sentinel-1 RTC + Sentinel-2 L2A (Copernicus / ESA) via Microsoft Planetary Computer", "provider": "Microsoft Planetary Computer (open data)", "quality": 0.92,
                         "last_updated": post_dt, "stale_after_hours": 24 * 14}
    # ---- Sentinel-2 (optical is optional; SAR-first if cloudy / absent)
    optical_post = optical_pre = None
    try:
        say("Searching Sentinel-2 scenes (cloud-masked with SCL)…")
        s2_post = imagery.pick_s2(bounds, post_dt.date(), post_dt.date() + __import__("datetime").timedelta(days=7), 95, prefer_near=post_dt.date())
        s2_pre = imagery.pick_s2(bounds, pre_dt.date() - __import__("datetime").timedelta(days=60), pre_dt.date() + __import__("datetime").timedelta(days=2), 85, prefer_near=pre_dt.date())
        if s2_post:
            say(f"Reading Sentinel-2 {s2_post['properties']['datetime'][:10]} (post, {s2_post['properties']['eo:cloud_cover']:.0f}% cloud)…")
            optical_post = imagery.read_s2(s2_post, t)
            passes.append({"sensor": "sentinel-2", "phase": "post", "acquired_at": datetime.fromisoformat(s2_post["properties"]["datetime"].replace("Z", "+00:00")),
                           "cloud_cover_pct": optical_post["cloud_pct"], "orbit": s2_post["properties"].get("s2:mgrs_tile", ""), "polarisation": "MSI L2A", "source": f"Microsoft Planetary Computer sentinel-2-l2a: {s2_post['id']}"})
        if s2_pre:
            say(f"Reading Sentinel-2 {s2_pre['properties']['datetime'][:10]} (pre)…")
            optical_pre = imagery.read_s2(s2_pre, t)
            passes.append({"sensor": "sentinel-2", "phase": "pre", "acquired_at": datetime.fromisoformat(s2_pre["properties"]["datetime"].replace("Z", "+00:00")),
                           "cloud_cover_pct": optical_pre["cloud_pct"], "orbit": s2_pre["properties"].get("s2:mgrs_tile", ""), "polarisation": "MSI L2A", "source": f"Microsoft Planetary Computer sentinel-2-l2a: {s2_pre['id']}"})
    except LiveDataError as e:
        log.warning("optical unavailable: %s", e)
    optical_ok = optical_post is not None and optical_pre is not None
    nan = np.full((t.height, t.width), np.nan, np.float32)
    # ---- terrain, land cover
    say("Reading Copernicus DEM and ESA WorldCover…")
    dem, dem_meta = imagery.read_dem(bounds, t)
    slope = compute_slope(dem, px)
    wc, wc_meta = imagery.read_worldcover(bounds, t)
    lc = np.vectorize(lambda v: WC_TO_LC.get(int(v), LC_VEG), otypes=[np.int8])(wc)
    builtup, water = wc == 50, wc == 80
    prov["dem"] = {"name": "Copernicus DEM GLO-30 (ESA)", "provider": "Microsoft Planetary Computer", "quality": 0.9, "last_updated": datetime(2021, 1, 1, tzinfo=timezone.utc), "stale_after_hours": 24 * 365 * 10}
    # ---- population (modelled)
    pop = np.zeros((t.height, t.width), np.float32)
    iso = p.get("iso3") or population.country_iso3(lat0, lon0)
    pop_meta: dict = {"available": False}
    if iso:
        try:
            say(f"Estimating population from WorldPop 2020 ({iso}) + WorldCover…")
            pad = 1500.0 / px
            from math import ceil
            n_pad = int(ceil(pad))
            dx, dy = (t.east - t.west) / t.width, (t.north - t.south) / t.height
            t_ext = GridTransform(t.west - n_pad * dx, t.south - n_pad * dy, t.east + n_pad * dx, t.north + n_pad * dy, t.height + 2 * n_pad, t.width + 2 * n_pad)
            wc_ext, _ = imagery.read_worldcover((t_ext.west, t_ext.south, t_ext.east, t_ext.north), t_ext)
            crop = (slice(n_pad, n_pad + t.height), slice(n_pad, n_pad + t.width))
            pop, pm = population.population_grid(t, wc_ext == 50, wc_ext == 80, t_ext, iso, crop)
            pop_meta = {"available": True, **pm}
            prov["population"] = {"name": pm["source"], "provider": "WorldPop (University of Southampton) + ESA WorldCover", "quality": 0.65, "last_updated": datetime(2020, 12, 31, tzinfo=timezone.utc),
                                  "stale_after_hours": 24 * 365 * 3, "notes": "Modelled estimate, not a census. No age structure: children/elderly vulnerability factors are unavailable."}
        except LiveDataError as e:
            log.warning("population unavailable: %s", e)
            pop_meta = {"available": False, "reason": str(e)}
    if not pop_meta.get("available"):
        say("Population data unavailable for this area; exposure will be reported as unknown (0)")
        prov["population"] = {"name": "Population - UNAVAILABLE", "provider": "none", "quality": 0.0, "availability": 0.0, "last_updated": datetime.now(timezone.utc), "stale_after_hours": 24,
                              "notes": pop_meta.get("reason", "No ISO country code resolved")}
    # ---- OpenStreetMap
    say("Fetching OpenStreetMap roads, facilities and places…")
    osm_roads = osm.fetch_roads(bounds)
    nodes, edges = osm.build_road_graph(osm_roads)
    feats = osm.parse_features(osm.fetch_features(bounds))
    w_, s_, e_, n_ = bounds
    inside = lambda o: s_ <= o["lat"] <= n_ and w_ <= o["lon"] <= e_  # noqa: E731
    facilities = [f for f in feats["facilities"] if inside(f)]
    shelters = [f for f in feats["shelters"] if inside(f)]
    places = [f for f in feats["places"] if inside(f)]
    now = datetime.now(timezone.utc)
    prov["roads"] = {"name": "OpenStreetMap roads (Overpass)", "provider": "OpenStreetMap contributors (ODbL)", "quality": 0.8, "last_updated": now, "stale_after_hours": 24 * 120}
    prov["infrastructure"] = {"name": "OpenStreetMap facilities (Overpass)", "provider": "OpenStreetMap contributors (ODbL)", "quality": 0.75, "last_updated": now, "stale_after_hours": 24 * 120,
                              "notes": "Shelter capacities are ASSUMED by facility type (OSM has no capacity); hospital->substation dependency is ASSUMED (nearest substation)."}
    # ---- bases: fire stations (preferred) else road nodes on opposite AOI edges
    stations = [f for f in facilities if f["kind"] == "emergency"]
    bases = []
    for f in stations[:2]:
        bases.append({"name": f["name"], "lat": f["lat"], "lon": f["lon"], "node": _nearest_node(nodes, f["lat"], f["lon"])})
    corners = [(n_, w_), (s_, e_)]
    for k in range(len(bases), 2):
        c = corners[k]
        nid = _nearest_node(nodes, *c)
        bases.append({"name": f"Assumed staging point {k + 1} (road node at AOI edge)", "lat": nodes[nid][0], "lon": nodes[nid][1], "node": nid})
    roster = p.get("roster") or DEFAULT_ROSTER
    resources = []
    for kind, n in roster.items():
        for i in range(n):
            b = bases[i % len(bases)]
            resources.append({"kind": kind, "name": f"{LABEL[kind]} {i + 1:02d}", "lat": b["lat"], "lon": b["lon"], "speed_kmh": SPEEDS[kind], "base": b["name"]})
    # ---- weather
    say("Fetching rainfall (Open-Meteo)…")
    try:
        wx = weather.rainfall_after(lat0, lon0, post_dt)
        prov["weather"] = {"name": wx["source"], "provider": "Open-Meteo", "quality": 0.8, "last_updated": now, "stale_after_hours": 12}
    except LiveDataError as e:
        wx = {"rainfall_mm": {"6": 0, "12": 0, "24": 0}, "river_level_trend_m_per_h": 0.0, "wind_kmh": 0.0, "source": "unavailable", "note": str(e)}
        prov["weather"] = {"name": "Weather - UNAVAILABLE", "provider": "none", "quality": 0.0, "availability": 0.0, "last_updated": now, "stale_after_hours": 12, "notes": str(e)}
    # ---- VIIRS hotspots (optional, needs a free NASA FIRMS key)
    hotspots: list = []
    if hazard == "wildfire":
        hotspots = _firms(bounds, post_dt)
    # ---- assemble
    quality = np.isfinite(pre_sar) & np.isfinite(post_sar) & (slope < 40)
    coast = ndi.distance_transform_edt(~water) * px if water.any() else np.full(dem.shape, 1e9)
    villages = []
    for pl in places:
        r, c = t.lonlat_to_rc(pl["lon"], pl["lat"])
        villages.append({"name": pl["name"], "lat": pl["lat"], "lon": pl["lon"], "r": int(np.clip(r, 0, t.height - 1)), "c": int(np.clip(c, 0, t.width - 1)), "pop": 0.0, "sigma_px": 5.0, "kind": pl["kind"]})
    cloud_pct = optical_post["cloud_pct"] if optical_post else None
    w = World(
        variant="real", hazard=hazard, t=t, seed=0, dem=dem, slope=slope, landcover=lc,
        pre_sar=pre_sar, post_sar=post_sar,
        pre_ndvi=optical_pre["ndvi"] if optical_ok else nan, post_ndvi=optical_post["ndvi"] if optical_ok else nan,
        pre_ndwi=optical_pre["ndwi"] if optical_ok else nan, post_ndwi=optical_post["ndwi"] if optical_ok else nan,
        pre_nbr=optical_pre["nbr"] if optical_ok else nan, post_nbr=optical_post["nbr"] if optical_ok else nan,
        cloud_mask=optical_post["cloud"] if optical_post else np.ones((t.height, t.width), bool), quality=quality, pop=pop.astype(np.float32), builtup=builtup,
        coast_dist_m=coast.astype(np.float32), cloud_pct=float(cloud_pct) if cloud_pct is not None else 100.0, hotspots=hotspots, villages=villages, facilities=facilities, shelters=shelters,
        resources=resources, bases=bases, road_nodes=nodes, road_edges=edges, weather=wx, passes=passes, truth=None,
        is_real=True, demographics_available=False, optical_available=optical_ok, rgb=optical_post["rgb"] if optical_post else None, provenance=prov,
        resources_note="HYPOTHETICAL roster: there is no real resource feed. Units are placed at the bases above so allocation can be demonstrated.",
    )
    w.provenance["population_meta"] = pop_meta
    ck.write_bytes(pickle.dumps(w))
    say("Real datasets assembled")
    return w


def _firms(bounds, post_dt) -> list[dict]:
    import os

    import requests

    key = os.environ.get("FIRMS_MAP_KEY")
    if not key:
        return []
    w, s, e, n = bounds
    try:
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_SP/{w},{s},{e},{n}/5/{post_dt.date()}"
        r = requests.get(url, timeout=60)
        lines = r.text.strip().splitlines()
        hdr = lines[0].split(",")
        out = []
        for ln in lines[1:]:
            v = dict(zip(hdr, ln.split(",")))
            out.append({"lat": float(v["latitude"]), "lon": float(v["longitude"]), "frp": float(v.get("frp", 0) or 0), "confidence": v.get("confidence", "nominal")})
        return out
    except Exception as ex:
        log.warning("FIRMS unavailable: %s", ex)
        return []
