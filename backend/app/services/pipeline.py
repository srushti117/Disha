"""Event processing pipeline (background job).

TRIGGER -> ACQUIRE -> PREPARE -> DETECT -> ASSESS -> PRIORITISE -> PREDICT -> PLAN   (automatic)
DISPATCH and VERIFY are operator-driven (resource assignment, field reports) and are derived from DB state.
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta

import h3
import numpy as np
from scipy import ndimage as ndi
from shapely.geometry import shape
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import SessionLocal
from ..demo.world import World, build_world
from ..engines import cascade as cascade_engine
from ..engines import roads as roads_engine
from ..engines.change_detection import ChangeDetectionEngine, DetectionInputs
from ..engines.geo import (cell_area_km2, cell_center, cell_polygon, cells_for_polygon, haversine_m, pixel_cell_labels,
                           polygon_area_km2, polygon_from_mask, zonal_mean, zonal_sum)
from ..engines.sensors import decide_sensors
from ..engines.vulnerability import VulnInput, vulnerability_score
from ..models import (AOI, DataSource, Event, H3Cell, HazardDetection, Infrastructure, PopulationExposure, Prediction,
                      PriorityResult, ProcessingJob, Resource, ResourceAssignment, RoadSegment, SatellitePass, Shelter, Vulnerability)
from .common import now, timeline
from .twin import event_config, recompute

log = logging.getLogger("disha.pipeline")
settings = get_settings()

STEPS = [("TRIGGER", "Trigger"), ("ACQUIRE", "Acquire"), ("PREPARE", "Prepare"), ("DETECT", "Detect"), ("ASSESS", "Assess"),
         ("PRIORITISE", "Prioritise"), ("PREDICT", "Predict"), ("PLAN", "Plan"), ("DISPATCH", "Dispatch"), ("VERIFY", "Verify")]
AUTO_STEPS = [s for s, _ in STEPS[:8]]

FACILITY_WEIGHT = {"hospital": 0.6, "power": 0.4, "water": 0.35, "school": 0.3, "emergency": 0.3, "comm": 0.2, "bridge": 0.25, "shelter": 0.2}
_WORLD_CACHE: dict[tuple, World] = {}


def event_dir(event_id: int):
    d = settings.data_dir / "events" / str(event_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_world(event: Event, progress=None) -> World:
    w = event.config["world"]
    if w.get("mode") == "live":
        from ..live.real_world import build_live_world

        return build_live_world(event.hazard, tuple(w["bounds"]), w["pre_end"], w["post_start"], w["post_end"], params=w.get("params", {}), progress=progress)
    key = (event.id, w["seed"], w["variant"], tuple(w["bounds"]), str(sorted(w["params"].items(), key=lambda kv: kv[0]))[:200])
    if key not in _WORLD_CACHE:
        if len(_WORLD_CACHE) > 4:
            _WORLD_CACHE.clear()
        _WORLD_CACHE[key] = build_world(event.hazard, tuple(w["bounds"]), seed=w["seed"], params=w["params"], variant=w["variant"])
    return _WORLD_CACHE[key]


def _village_demographics(world: World) -> None:
    rng = np.random.default_rng(world.seed + 1)
    for v in world.villages:
        v.setdefault("children_frac", float(rng.uniform(0.17, 0.30)))
        v.setdefault("elderly_frac", float(rng.uniform(0.06, 0.15)))
        v.setdefault("housing_vuln", float(rng.uniform(0.25, 0.85)))


class Job:
    def __init__(self, db: Session, job: ProcessingJob, pace: float):
        self.db, self.job, self.pace = db, job, pace
        job.steps = [{"key": k, "label": l, "status": "pending", "detail": ""} for k, l in STEPS]
        job.status, job.started_at = "running", now()
        db.commit()

    def begin(self, key: str):
        self._set(key, "running")
        self.job.current_step = key
        self.job.progress = round(AUTO_STEPS.index(key) / len(AUTO_STEPS), 3) if key in AUTO_STEPS else self.job.progress
        self.db.commit()
        if self.pace:
            time.sleep(self.pace)

    def note(self, key: str, detail: str):
        """Live progress text for long-running steps (shown in the pipeline UI)."""
        self._set(key, "running", detail)
        self.db.commit()

    def done(self, key: str, detail: str = ""):
        self._set(key, "done", detail)
        self.db.commit()

    def _set(self, key, status, detail=None):
        steps = [dict(s) for s in self.job.steps]
        for s in steps:
            if s["key"] == key:
                s["status"] = status
                if detail is not None:
                    s["detail"] = detail
                s["at"] = now().isoformat()
        self.job.steps = steps


def start_job(db: Session, event: Event) -> ProcessingJob:
    job = ProcessingJob(event_id=event.id, kind="full_analysis", status="queued")
    db.add(job)
    event.status = "processing"
    db.commit()
    return job


def run_analysis(event_id: int, job_id: int, pace: float = 0.0, keep_history: bool = False) -> None:
    db = SessionLocal()
    try:
        event, job = db.get(Event, event_id), db.get(ProcessingJob, job_id)
        j = Job(db, job, pace)
        try:
            _run(db, event, j, keep_history)
            job.status, job.progress, job.finished_at = "succeeded", 1.0, now()
            event.status = "active"
            for s in ("DISPATCH", "VERIFY"):
                j._set(s, "awaiting", "Operator action required")
            db.commit()
        except Exception as e:  # recorded, never silent
            log.exception("analysis failed")
            db.rollback()
            job = db.get(ProcessingJob, job_id)
            job.status, job.error, job.finished_at = "failed", f"{type(e).__name__}: {e}", now()
            db.get(Event, event_id).status = "failed"
            db.commit()
    finally:
        db.close()


def _clear_derived(db: Session, event_id: int, keep_history: bool = False):
    models = [HazardDetection, H3Cell, PopulationExposure, Vulnerability, Infrastructure, RoadSegment, Shelter, SatellitePass, Prediction]
    if not keep_history:
        models.append(PriorityResult)
    for m in models:
        db.execute(delete(m).where(m.event_id == event_id))
    from ..models import Route, Alert, Notification
    db.execute(delete(Route).where(Route.event_id == event_id))
    db.execute(delete(DataSource).where(DataSource.event_id == event_id))
    if not keep_history:
        for m in (Notification, Alert):
            db.execute(delete(m).where(m.event_id == event_id))
        db.execute(delete(ResourceAssignment).where(ResourceAssignment.event_id == event_id))
        db.query(Resource).filter(Resource.event_id == event_id).delete()
    db.flush()


def _run(db: Session, event: Event, j: Job, keep_history: bool = False):
    cfgw = event.config["world"]
    aoi = db.scalars(select(AOI).where(AOI.event_id == event.id)).first()
    res = event.h3_resolution
    # ------------------------------------------------------------------ TRIGGER
    j.begin("TRIGGER")
    old_nos = {c.h3_index: c.cell_no for c in db.scalars(select(H3Cell).where(H3Cell.event_id == event.id))} if keep_history else {}
    _clear_derived(db, event.id, keep_history)
    if not keep_history:
        event.assessment_version = 0
        event.config = {k: v for k, v in event.config.items() if k not in ("prev_isolated", "prev_hospitals", "road_hist", "coverage")}
        timeline(db, event.id, "alert", f"{event.hazard.title()} alert received", f"Event {event.code}: {event.name}. AOI {aoi.area_km2:.0f} km2.")
    else:
        timeline(db, event.id, "satellite", "New satellite pass received (simulated)", f"Re-analysing; previous assessment v{event.assessment_version} retained for comparison.")
    j.done("TRIGGER", f"Alert accepted for {event.name}")

    # ------------------------------------------------------------------ ACQUIRE
    j.begin("ACQUIRE")
    world = get_world(event, progress=lambda m: j.note("ACQUIRE", m))
    live = world.is_real
    if not live:
        _village_demographics(world)
    t0 = now()
    from datetime import datetime
    if live:
        for ps in world.passes:
            db.add(SatellitePass(event_id=event.id, sensor=ps["sensor"], phase=ps["phase"], acquired_at=ps["acquired_at"], cloud_cover_pct=ps["cloud_cover_pct"], polarisation=ps["polarisation"],
                                 orbit=ps["orbit"][:32], is_simulated=False, source=ps["source"][:120]))
        post = max(ps["acquired_at"] for ps in world.passes if ps["sensor"] == "sentinel-1" and ps["phase"] == "post")
        for key, pv in world.provenance.items():
            if key == "population_meta":
                continue
            db.add(DataSource(event_id=event.id, key=key, name=pv["name"], provider=pv["provider"], is_simulated=False, quality=pv["quality"], availability=pv.get("availability", 1.0),
                              last_updated=pv["last_updated"], stale_after_hours=pv["stale_after_hours"], notes=pv.get("notes", "")))
        db.add(DataSource(event_id=event.id, key="resources", name="Response resources (HYPOTHETICAL roster)", provider="none (no real resource feed)", is_simulated=True, quality=0.5, availability=1.0,
                          last_updated=t0, stale_after_hours=24, notes=world.resources_note))
        decision = decide_sensors(world.cloud_pct if world.optical_available else None, world.optical_available, True, event.hazard, thermal_available=bool(world.hotspots))
        if not world.optical_available:
            extra = "; the post-event Sentinel-2 image is shown for context only." if world.rgb is not None else "."
            decision.explanation = f"No usable pre-event optical scene for a before/after comparison{extra} Sentinel-1 SAR is the sole detection source (all-weather, day and night)."
        title = "Satellite passes retrieved (Sentinel-1 RTC / Sentinel-2 L2A, Copernicus)"
    else:
        pre = cfgw.get("pre_date")
        post = now() - timedelta(minutes=38)
        pre_dt = datetime.fromisoformat(pre) if pre else post - timedelta(days=12)
        sensors = [("sentinel-1", "pre", pre_dt, None, "IW GRD VV/VH"), ("sentinel-1", "post", post, None, "IW GRD VV/VH"),
                   ("sentinel-2", "pre", pre_dt, 5.0, "MSI L2A"), ("sentinel-2", "post", post, world.cloud_pct, "MSI L2A")]
        if event.hazard == "wildfire":
            sensors.append(("viirs", "post", post, None, "375 m active fire"))
        for s_, ph, ts, cc, pol in sensors:
            db.add(SatellitePass(event_id=event.id, sensor=s_, phase=ph, acquired_at=ts, cloud_cover_pct=cc, polarisation=pol,
                                 orbit="SIMULATED", is_simulated=True, source="DEMO / SIMULATED DATA (no live retrieval)"))
        for key, name, prov, q, stale in [
            ("satellite", "Sentinel-1/2 (simulated passes)", "DEMO / SIMULATED", 0.94, 72), ("dem", "DEM (SRTM-style, simulated)", "DEMO / SIMULATED", 0.9, 24 * 365),
            ("weather", "Rainfall / river / wind forecast (simulated)", "DEMO / SIMULATED", 0.8, 12), ("population", "WorldPop-style population (simulated)", "DEMO / SIMULATED", 0.75, 24 * 365),
            ("roads", "OSM-compatible road network (simulated)", "DEMO / SIMULATED", 0.85, 24 * 120), ("infrastructure", "Critical infrastructure (placeholder facilities)", "DEMO / SIMULATED", 0.8, 24 * 120)]:
            lu = {"satellite": post, "weather": t0, "population": t0 - timedelta(days=35), "roads": t0 - timedelta(days=20),
                  "infrastructure": t0 - timedelta(days=20), "dem": t0 - timedelta(days=300)}[key]
            db.add(DataSource(event_id=event.id, key=key, name=name, provider=prov, is_simulated=True, quality=q, availability=1.0, last_updated=lu, stale_after_hours=stale,
                              notes="Demonstration data. Not live."))
        decision = decide_sensors(world.cloud_pct, True, True, event.hazard, thermal_available=event.hazard == "wildfire")
        title = "Satellite passes acquired (simulated)"
    event.last_satellite_pass = post
    event.config = {**event.config, "weather": world.weather, "sensor_decision": decision.to_dict(),
                    "road_nodes": {str(k): v for k, v in world.road_nodes.items()}, "bases": world.bases, "data_mode": "live" if live else "simulated"}
    timeline(db, event.id, "satellite", title, f"Post-event pass {post.strftime('%Y-%m-%d %H:%M')} UTC. {decision.explanation}")
    j.done("ACQUIRE", decision.explanation)

    # ------------------------------------------------------------------ PREPARE
    j.begin("PREPARE")
    if live:
        prep = (f"Sentinel-1 RTC (terrain-corrected gamma0) resampled to a shared {world.t.height}x{world.t.width} grid (~{world.t.pixel_size_m[0]:.0f} m, multilooked in linear power); "
                f"same orbit track pre/post; Copernicus DEM slope; Sentinel-2 SCL cloud mask; 5x5 speckle filter applied in the detector.")
    else:
        prep = (f"Calibration to sigma0 dB (inputs pre-calibrated); co-registration verified on shared {world.t.height}x{world.t.width} grid "
                f"(~{world.t.pixel_size_m[0]:.0f} m px); cloud mask {world.cloud_pct:.0f}% of optical; speckle filter 5x5 multilook applied in detector.")
    db.flush()
    j.done("PREPARE", prep)

    # ------------------------------------------------------------------ DETECT
    j.begin("DETECT")
    inp = DetectionInputs(event.hazard, world.pre_sar, world.post_sar, world.pre_ndvi, world.post_ndvi, world.pre_ndwi, world.post_ndwi,
                          world.pre_nbr, world.post_nbr, world.cloud_mask, world.quality, world.dem, world.slope, world.builtup,
                          world.coast_dist_m, world.hotspots, world.t, decision.optical_weight, world.t.pixel_size_m[0])
    det = ChangeDetectionEngine().detect(inp, prefer=(event.config or {}).get("detector", "rule_based"))
    px_km2 = world.t.pixel_size_m[0] * world.t.pixel_size_m[1] / 1e6
    area = float(det.mask.sum() * px_km2)
    footprint = polygon_from_mask(world.t, det.mask)
    db.add(HazardDetection(event_id=event.id, hazard=event.hazard, model_name=det.model_name, model_version=det.model_version,
                           sensor_mode=decision.mode, sensor_explanation=decision.explanation, detected_area_km2=round(area, 3),
                           mean_confidence=round(float(det.confidence[det.mask].mean()), 3) if det.mask.any() else 0.0,
                           mean_severity=round(float(det.severity[det.mask].mean()), 3) if det.mask.any() else 0.0,
                           outputs={**det.outputs, "notes": det.notes}, stats=det.stats, footprint=footprint, is_simulated_input=not live))
    np.savez_compressed(event_dir(event.id) / "rasters.npz", pre_sar=world.pre_sar, post_sar=world.post_sar, mask=det.mask, severity=det.severity,
                        confidence=det.confidence, post_ndvi=world.post_ndvi, pre_ndvi=world.pre_ndvi, cloud=world.cloud_mask, dem=world.dem,
                        pop=world.pop, bounds=np.array(world.t.bounds), **({"rgb": world.rgb} if world.rgb is not None else {}), **{f"x_{k}": v for k, v in det.extra_layers.items()})
    event.config = {**event.config, "has_rgb": world.rgb is not None}
    timeline(db, event.id, "detection", f"Change detected: {area:.1f} km2 affected", f"{det.model_name} v{det.model_version}; sensor mode {decision.mode}.")
    j.done("DETECT", f"{area:.1f} km2 detected by {det.model_name} ({decision.mode})")

    # ------------------------------------------------------------------ ASSESS
    j.begin("ASSESS")
    _assess(db, event, world, det, decision, res, aoi, old_nos, skip_resources=keep_history)
    j.done("ASSESS", "Population, vulnerability, infrastructure, roads and cascades evaluated per H3 cell")

    # ------------------------------------------------------------------ PRIORITISE + PREDICT
    j.begin("PRIORITISE")
    out = recompute(db, event, trigger="new_pass" if keep_history else "analysis", predict=False, announce=keep_history)
    s = out["summary"]
    timeline(db, event.id, "priority", "Priority generated", f"P1={s['p1']} P2={s['p2']} P3={s['p3']} P4={s['p4']}; {s['population_at_risk']:,} people at high risk.")
    top = db.scalars(select(H3Cell).where(H3Cell.event_id == event.id, H3Cell.priority_level == "P1").order_by(H3Cell.cell_no).limit(1)).first()
    if top:
        timeline(db, event.id, "priority", f"P1 Cell {top.cell_no:02d} identified", "; ".join(r["label"] for r in top.reason_codes[:3]), top.h3_index)
    j.done("PRIORITISE", f"P1={s['p1']} P2={s['p2']} P3={s['p3']} P4={s['p4']}")

    j.begin("PREDICT")
    from .twin import run_predictions
    run_predictions(db, event, event.assessment_version)
    j.done("PREDICT", "6/12/24/48 h risk expansion estimates (heuristic model, uncalibrated)")

    # ------------------------------------------------------------------ PLAN
    j.begin("PLAN")
    from . import response
    n_routes = response.precompute_routes(db, event)
    plan = response.evacuation_plan(db, event)
    timeline(db, event.id, "plan", "Response plan prepared", f"{n_routes} rescue route sets; evacuation: {plan['summary']['people_assigned']:,}/{plan['summary']['people_needing_shelter']:,} people placed.")
    from .common import persist_alerts
    if not keep_history:
        persist_alerts(db, event, build_first_alerts(db, event, out, plan))
    event.severity = "extreme" if s["p1"] >= 10 else "high" if s["p1"] >= 3 else "moderate"
    j.done("PLAN", f"{n_routes} route sets, evacuation plan, resource roster ready")
    db.commit()


def build_first_alerts(db: Session, event: Event, out: dict, plan: dict | None = None) -> list[dict]:
    from ..engines.alerts import build_alerts
    cells = db.scalars(select(H3Cell).where(H3Cell.event_id == event.id)).all()
    hosp = [{"name": i.name, "reason": i.risk_reason, "h3_index": i.h3_index} for i in
            db.scalars(select(Infrastructure).where(Infrastructure.event_id == event.id, Infrastructure.kind == "hospital", Infrastructure.risk >= 0.25))]
    iso = [c.h3_index for c in cells if c.population_isolated > 0]
    from ..models import Prediction as P
    n_pred = db.query(P).filter(P.event_id == event.id, P.horizon_h == 6, P.predicted_level == "P1", P.current_level != "P1", P.expansion_probability >= 0.5).count()
    ctx = {"isolated_cells": iso, "isolated_pop": sum(c.population_isolated for c in cells), "hospitals_at_risk": hosp, "predicted_p1_escalations": n_pred,
           "shelter_util": plan["summary"]["shelter_utilisation"] if plan else []}
    return build_alerts(event_config(event)["alerts"], None, out["summary"], [], ctx)


def _assess(db: Session, event: Event, world: World, det, decision, res: int, aoi: AOI, old_nos: dict | None = None, skip_resources: bool = False):
    cfg = event_config(event)
    t = world.t
    cell_ids = cells_for_polygon(aoi.geom, res)
    if not cell_ids:
        raise ValueError("AOI contains no H3 cells at this resolution; enlarge the AOI or raise the resolution.")
    n = len(cell_ids)
    labels = pixel_cell_labels(t, cell_ids, res)
    mask = det.mask
    mf = mask.astype(float)
    hf = zonal_mean(labels, mf, n)
    sev_sum = zonal_sum(labels, np.where(mask, det.severity, 0), n)
    mask_n = zonal_sum(labels, mf, n)
    sev_aff = np.divide(sev_sum, mask_n, out=np.zeros(n), where=mask_n > 0)
    sev_cell = sev_aff * np.minimum(1.0, hf / 0.4) ** 0.6
    conf_sum = zonal_sum(labels, np.where(mask, det.confidence, 0), n)
    conf_aff = np.divide(conf_sum, mask_n, out=np.zeros(n), where=mask_n > 0)
    valid_frac = zonal_mean(labels, world.quality.astype(float), n)
    det_conf = np.where(mask_n > 0, conf_aff, 0.85 * valid_frac)
    elev = zonal_mean(labels, world.dem.astype(float), n)
    slope = zonal_mean(labels, world.slope.astype(float), n)
    pop = zonal_sum(labels, world.pop.astype(float), n)
    exposed = zonal_sum(labels, np.where(mask, world.pop, 0), n)
    high = zonal_sum(labels, np.where(mask & (det.severity >= 0.5), world.pop, 0), n)
    # demographics: nearest-village attribute raster, population-weighted per cell (DEMO estimates; unavailable for live data)
    live = world.is_real
    if world.demographics_available and world.villages:
        seeds = np.zeros(mask.shape, np.int32)
        for k, v in enumerate(world.villages):
            seeds[int(np.clip(v["r"], 0, t.height - 1)), int(np.clip(v["c"], 0, t.width - 1))] = k + 1
        idx = ndi.distance_transform_edt(seeds == 0, return_distances=False, return_indices=True)
        nearest = seeds[idx[0], idx[1]] - 1

        def vattr(name):
            arr = np.array([v[name] for v in world.villages])
            return arr[nearest]

        kids = zonal_mean(labels, vattr("children_frac"), n, weights=world.pop)
        old = zonal_mean(labels, vattr("elderly_frac"), n, weights=world.pop)
        housing = zonal_mean(labels, vattr("housing_vuln"), n, weights=world.pop)
        demo_ok = True
    else:
        kids = old = housing = np.zeros(n)
        demo_ok = False  # real data: no age structure available -> factors are skipped, not invented

    # ---- infrastructure
    facs = []
    for f in world.facilities:
        c = h3.latlng_to_cell(f["lat"], f["lon"], res)
        facs.append({**f, "h3_index": c})
    infra_rows: dict[str, Infrastructure] = {}
    for f in facs:
        row = Infrastructure(event_id=event.id, kind=f["kind"], name=f["name"], geom={"type": "Point", "coordinates": [f["lon"], f["lat"]]},
                             h3_index=f["h3_index"], capacity=f.get("capacity"), depends_on=f.get("depends_on", []),
                             source=(f"OpenStreetMap {f.get('osm_id', '')}" if live else "DEMO / SIMULATED placeholder facility"))
        db.add(row)
        infra_rows[f["name"]] = row

    # ---- roads
    edges = []
    for e in world.road_edges:
        edges.append(dict(e))
    segs = roads_engine.classify_segments(edges, world.road_nodes, t, mask, world.quality, res)
    for s in segs:
        line = s["coords"] if len(s["coords"]) >= 2 else [[world.road_nodes[s["u"]][1], world.road_nodes[s["u"]][0]], [world.road_nodes[s["v"]][1], world.road_nodes[s["v"]][0]]]
        db.add(RoadSegment(event_id=event.id, name=s["name"][:160], road_class=s["class"], geom={"type": "LineString", "coordinates": line},
                           u=s["u"], v=s["v"], length_m=s["length_m"], is_bridge=s["is_bridge"], status=s["status"], flooded_fraction=s["flooded_fraction"],
                           is_critical=s["is_critical"], h3_indices=s["h3_indices"], source=("OpenStreetMap (Overpass)" if live else "DEMO / SIMULATED (OSM-compatible)")))
        if s["is_bridge"]:
            mlon, mlat = line[len(line) // 2]
            bc = h3.latlng_to_cell(mlat, mlon, res)
            bname = s["name"] if s["name"] not in infra_rows else f"{s['name']} (bridge {len(infra_rows)})"
            facs.append({"kind": "bridge", "name": bname, "lat": mlat, "lon": mlon, "h3_index": bc, "depends_on": [], "status": s["status"]})
            row = Infrastructure(event_id=event.id, kind="bridge", name=bname[:160], geom={"type": "Point", "coordinates": [mlon, mlat]}, h3_index=bc,
                                 status={"blocked": "impaired", "potentially_blocked": "at_risk"}.get(s["status"], "operational"),
                                 risk={"blocked": 0.9, "potentially_blocked": 0.5}.get(s["status"], 0.05),
                                 risk_reason=f"Bridge status: {s['status'].replace('_', ' ')}" if s["status"] != "open" else "",
                                 source=("OpenStreetMap (bridge=yes)" if live else "DEMO / SIMULATED placeholder facility"))
            db.add(row)
            infra_rows[bname] = row
            s["bridge_name"] = bname
    centers = {c: cell_center(c) for c in cell_ids}
    base_nodes = [b["node"] for b in world.bases]
    acc = roads_engine.cell_access(segs, world.road_nodes, cell_ids, centers, base_nodes)
    bdeps = roads_engine.bridge_dependents(segs, base_nodes)
    if live:  # many real bridges share names; keep the dependents map unambiguous
        bdeps = {f"{k}": v for k, v in bdeps.items()}
    node_cell = {k: h3.latlng_to_cell(la, lo, res) for k, (la, lo) in world.road_nodes.items()}

    cid = {c: i for i, c in enumerate(cell_ids)}
    counts = {c: {} for c in cell_ids}
    for f in facs:
        if f["h3_index"] in counts:
            counts[f["h3_index"]][f["kind"]] = counts[f["h3_index"]].get(f["kind"], 0) + 1
    shelters = []
    for s in world.shelters:
        c = h3.latlng_to_cell(s["lat"], s["lon"], res)
        r, cc = t.lonlat_to_rc(s["lon"], s["lat"])
        r, cc = int(np.clip(r, 0, t.height - 1)), int(np.clip(cc, 0, t.width - 1))
        haz = bool(mask[r, cc]) or (c in cid and hf[cid[c]] > 0.25)
        row = Shelter(event_id=event.id, name=s["name"], geom={"type": "Point", "coordinates": [s["lon"], s["lat"]]}, h3_index=c,
                      capacity=s["capacity"], occupied=s["occupied"], in_hazard_zone=haz,
                      source=("OpenStreetMap " + s.get("osm_id", "") + " (capacity ASSUMED by facility type)") if live else "DEMO / SIMULATED placeholder facility")
        db.add(row)
        shelters.append({**s, "h3_index": c, "haz": haz})
    safe_sh = [s for s in shelters if not s["haz"]]

    # hazard exposure per cell for cascade (own severity or 0.6 x neighbour)
    sev_map = {c: float(sev_cell[cid[c]]) for c in cell_ids}
    cell_hazard = {c: max(sev_map[c], 0.6 * max([sev_map.get(nb, 0.0) for nb in h3.grid_ring(c, 1)] or [0.0])) for c in cell_ids}
    loss_map = {c: acc[c]["access_loss"] for c in cell_ids}
    casc = cascade_engine.facility_cascades(facs, cell_hazard, loss_map, bdeps, node_cell)
    for name, r in casc["facilities"].items():
        row = infra_rows.get(name)
        if row is not None and row.kind != "bridge":
            row.risk, row.status, row.risk_reason = r["risk"], r["status"], r["reason"]

    hospitals = [f for f in facs if f["kind"] == "hospital"]
    pa = polygon_area_km2
    cells_rows = []
    pe_rows, v_rows = [], []
    for i, c in enumerate(cell_ids):
        area = cell_area_km2(c)
        lat, lon = centers[c]
        cnt = counts[c]
        ring = h3.grid_ring(c, 1)
        near = {k: sum(counts.get(nb, {}).get(k, 0) for nb in ring) for k in FACILITY_WEIGHT}
        presence = min(1.0, sum(FACILITY_WEIGHT[k] * cnt.get(k, 0) for k in FACILITY_WEIGHT) + 0.5 * sum(FACILITY_WEIGHT[k] * near[k] for k in FACILITY_WEIGHT))
        fc = {**cnt, "hospital_near": cnt.get("hospital", 0) + near["hospital"], "school": cnt.get("school", 0), "power": cnt.get("power", 0)}
        a = acc[c]
        nh_km = min((haversine_m(lat, lon, h["lat"], h["lon"]) for h in hospitals), default=None)
        nh_km = None if nh_km is None else nh_km / 1000
        vin = VulnInput(density_per_km2=pop[i] / area, children_frac=float(kids[i]) if (pop[i] > 0 and demo_ok) else None, elderly_frac=float(old[i]) if (pop[i] > 0 and demo_ok) else None,
                        housing_vulnerability=float(housing[i]) if (pop[i] > 0 and demo_ok) else None, nearest_hospital_km=nh_km, isolated=a["isolated"],
                        access_loss=a["access_loss"], severity=float(sev_cell[i]), demographics_estimated=True)
        vs, vmeta = vulnerability_score(vin, cfg["vuln_weights"])
        if pop[i] < 1:
            vs = 0.0  # nobody lives here: vulnerability is not defined
        vulnerable = int(round(exposed[i] * ((kids[i] + old[i]) if (pop[i] > 0 and demo_ok) else 0)))
        ns = min((haversine_m(lat, lon, s["lat"], s["lon"]) for s in safe_sh), default=None)
        cc = casc["cells"].get(c, {"cascade_risk": 0.0, "cascade_reason": "", "affected_dependencies": []})
        iso_pop = int(round(pop[i])) if a["isolated"] else 0
        base = {"severity": float(sev_cell[i]), "confidence": float(det_conf[i]), "exposed": int(round(exposed[i]))}
        cells_rows.append(H3Cell(
            event_id=event.id, h3_index=c, cell_no=(old_nos or {}).get(c), geom=cell_polygon(c), lat=lat, lon=lon, area_km2=area, hazard_fraction=float(hf[i]),
            affected_area_km2=float(hf[i] * area), severity=base["severity"], detection_confidence=base["confidence"], elevation_m=float(elev[i]),
            slope_deg=float(slope[i]), population=int(round(pop[i])), population_exposed=base["exposed"], population_high_risk=int(round(high[i])),
            population_isolated=iso_pop, vulnerable_population=vulnerable, buildings=0 if live else int(round(pop[i] / 4.2)), vulnerability_score=vs,
            critical_facility_count=sum(cnt.values()), access_loss=a["access_loss"], road_status=a["road_status"],
            nearest_shelter_km=None if ns is None else round(ns / 1000, 2), cascade_risk=cc["cascade_risk"], cascade_reason=cc["cascade_reason"],
            affected_dependencies=cc["affected_dependencies"],
            components={"base": base, "infra_presence": presence, "facility_counts": fc, "road_m": a["road_m"], "vulnerability": vmeta,
                        "buildings_note": "Building count not available for live data." if live else "Buildings estimated as population / 4.2 (demo estimate).",
                        "population_note": ("Modelled estimate: WorldPop 2020 (1 km) disaggregated onto ESA WorldCover built-up. Not a census. Children/elderly shares unavailable (vulnerability uses the remaining factors)."
                                            if live else "Simulated population and demographics (demonstration data).")},
        ))
        pe_rows.append(PopulationExposure(event_id=event.id, h3_index=c, total=int(round(pop[i])), exposed=base["exposed"], high_risk=int(round(high[i])),
                                          potentially_isolated=iso_pop, exposure_norm=0.0,
                                          source="WorldPop 2020 1 km + ESA WorldCover (modelled)" if live else "DEMO / SIMULATED (WorldPop-style)", is_estimated=True))
        v_rows.append(Vulnerability(event_id=event.id, h3_index=c, score=vs, factors=vmeta["factors"], children_frac=float(kids[i]) if (pop[i] > 0 and demo_ok) else None,
                                    elderly_frac=float(old[i]) if (pop[i] > 0 and demo_ok) else None,
                                    source="Not available (no age structure in live data)" if live else "DEMO / SIMULATED estimate"))
    db.add_all(cells_rows + pe_rows + v_rows)
    db.flush()
    # re-key resources for this event
    for r in ([] if skip_resources else world.resources):
        db.add(Resource(event_id=event.id, kind=r["kind"], name=r["name"], status="available", lat=r["lat"], lon=r["lon"], speed_kmh=r["speed_kmh"]))
    db.flush()
