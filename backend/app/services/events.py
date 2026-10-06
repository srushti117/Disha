"""Event + AOI creation (5 AOI methods) shared by API, seed and tests."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from shapely.geometry import box, mapping, shape
from sqlalchemy.orm import Session

from ..demo.scenarios import ADMIN_AREAS, LIVE_SCENARIOS, SCENARIOS, scenario_bounds
from ..core.config import get_settings
from ..engines.geo import geojson_bbox_polygon, polygon_area_km2
from ..models import AOI, Event
from .common import audit, timeline

MAX_AOI_KM2 = 900.0
LIVE_MAX_AOI_KM2 = 400.0  # real-data retrieval cost grows with area
MIN_AOI_KM2 = 4.0
HAZARDS = ("flood", "wildfire", "landslide", "cyclone")


def next_code(db: Session) -> str:
    n = db.query(Event).count() + 1
    while db.query(Event).filter(Event.code == f"EVT-{n:04d}").count():
        n += 1
    return f"EVT-{n:04d}"


def resolve_aoi(method: str, payload: dict) -> tuple[dict, str]:
    """Return (GeoJSON polygon, name). Validates geometry and size."""
    if method == "draw" or method == "upload":
        gj = payload.get("geojson")
        if isinstance(gj, str):
            gj = json.loads(gj)
        if not gj:
            raise ValueError("geojson is required")
        if gj.get("type") == "FeatureCollection":
            gj = gj["features"][0]
        if gj.get("type") == "Feature":
            gj = gj["geometry"]
        g = shape(gj)
        if g.geom_type == "MultiPolygon":
            g = max(g.geoms, key=lambda p: p.area)
        if g.geom_type != "Polygon" or not g.is_valid:
            raise ValueError("AOI must be a valid Polygon")
        geom = mapping(g)
        name = payload.get("name") or ("Uploaded AOI" if method == "upload" else "Drawn AOI")
    elif method == "coordinates":
        w, s, e, n = (float(payload[k]) for k in ("west", "south", "east", "north"))
        if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
            raise ValueError("Invalid coordinate bounds")
        geom, name = geojson_bbox_polygon(w, s, e, n), payload.get("name") or "Coordinate AOI"
    elif method == "admin":
        a = next((x for x in ADMIN_AREAS if x["id"] == payload.get("admin_id")), None)
        if not a:
            raise ValueError("Unknown administrative area")
        geom, name = geojson_bbox_polygon(*a["bounds"]), a["name"]
    elif method == "demo":
        key = payload.get("scenario_key")
        sc_ = SCENARIOS.get(key) or LIVE_SCENARIOS.get(key)
        if not sc_:
            raise ValueError("Unknown scenario")
        geom, name = geojson_bbox_polygon(*scenario_bounds(key)), sc_["title"] + " AOI"
    else:
        raise ValueError(f"Unknown AOI method '{method}'")
    area = polygon_area_km2(geom)
    if area < MIN_AOI_KM2:
        raise ValueError(f"AOI too small ({area:.1f} km2); minimum is {MIN_AOI_KM2:.0f} km2")
    if area > MAX_AOI_KM2:
        raise ValueError(f"AOI too large ({area:.0f} km2); maximum is {MAX_AOI_KM2:.0f} km2 for this build")
    return geom, name


def create_event(db: Session, user, *, name: str, hazard: str, aoi_method: str, aoi_payload: dict, scenario_key: str | None = None,
                 h3_resolution: int | None = None, start_date: datetime | None = None, severity: str = "unknown",
                 data_mode: str = "simulated", live: dict | None = None) -> Event:
    if hazard not in HAZARDS:
        raise ValueError(f"Hazard must be one of {HAZARDS}")
    live_sc = LIVE_SCENARIOS.get(scenario_key) if scenario_key else None
    sc = SCENARIOS.get(scenario_key) if scenario_key else None
    if scenario_key and not (sc or live_sc):
        raise ValueError("Unknown scenario")
    if sc or live_sc:
        hazard = (sc or live_sc)["hazard"]
    is_live = bool(live_sc) or data_mode == "live"
    geom, aoi_name = resolve_aoi(aoi_method, {**aoi_payload, **({"scenario_key": scenario_key} if (sc or live_sc) else {})})
    bounds = shape(geom).bounds
    if is_live:
        if polygon_area_km2(geom) > LIVE_MAX_AOI_KM2:
            raise ValueError(f"AOI too large for real-data retrieval ({polygon_area_km2(geom):.0f} km2); maximum is {LIVE_MAX_AOI_KM2:.0f} km2")
        lv = live_sc or (live or {})
        try:
            d_pre, d_ps, d_pe = (datetime.fromisoformat(str(lv[k])[:10]) for k in ("pre_end", "post_start", "post_end"))
        except (KeyError, ValueError) as ex:
            raise ValueError("Real-data events need pre_end, post_start and post_end dates (YYYY-MM-DD)") from ex
        if not (d_pre < d_ps <= d_pe):
            raise ValueError("Dates must satisfy: pre_end < post_start <= post_end")
        if d_pe > datetime.now() + timedelta(days=1):
            raise ValueError("post_end cannot be in the future")
        world = {"mode": "live", "bounds": list(bounds), "pre_end": str(lv["pre_end"])[:10], "post_start": str(lv["post_start"])[:10], "post_end": str(lv["post_end"])[:10],
                 "params": dict((live_sc or {}).get("params", {}), **({"iso3": lv["iso3"]} if lv.get("iso3") else {})), "seed": 0, "variant": "real"}
        if live_sc:
            geom = geojson_bbox_polygon(*scenario_bounds(scenario_key))
            world["bounds"] = list(scenario_bounds(scenario_key))
    elif sc:
        world = {"variant": sc["variant"], "seed": sc["seed"], "params": sc["params"], "bounds": list(scenario_bounds(scenario_key)),
                 "pre_date": sc["pre_date"].isoformat(), "post_date": sc["post_date"].isoformat()}
        geom = geojson_bbox_polygon(*world["bounds"]) if aoi_method == "demo" else geom
    else:
        seed = abs(hash((round(bounds[0], 3), round(bounds[1], 3), hazard))) % 10_000
        defaults = {"flood": ("flood_river", {"cloud_pct": 70, "pop_total": 60_000}), "wildfire": ("wildfire", {"cloud_pct": 25, "pop_total": 8_000}),
                    "landslide": ("landslide", {"cloud_pct": 80, "pop_total": 15_000}), "cyclone": ("cyclone", {"cloud_pct": 90, "pop_total": 50_000})}[hazard]
        world = {"variant": defaults[0], "seed": seed, "params": defaults[1], "bounds": list(bounds)}
    res = h3_resolution or get_settings().h3_resolution
    ref = sc or live_sc
    ev = Event(code=next_code(db), name=name or (ref["name"] if ref else f"{hazard.title()} event"), hazard=hazard, scenario_key=scenario_key,
               is_demo=not is_live, start_date=start_date or (ref["event_start"] if ref else datetime.now(timezone.utc)), severity=ref["severity"] if ref else severity,
               status="created", h3_resolution=res, config={"world": world}, created_by=getattr(user, "id", None))
    db.add(ev)
    db.flush()
    db.add(AOI(event_id=ev.id, name=aoi_name, method=aoi_method, geom=geom, area_km2=polygon_area_km2(geom)))
    timeline(db, ev.id, "created", f"Event {ev.code} created", f"{hazard.title()} - AOI via {aoi_method} - {'REAL open data' if is_live else 'simulated data'}")
    audit(db, user, "event.create", ev.code, ev.id, detail={"hazard": hazard, "aoi_method": aoi_method, "data_mode": "live" if is_live else "simulated"})
    db.flush()
    return ev
