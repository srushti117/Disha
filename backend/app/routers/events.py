"""Events, processing, map, detections, priorities, predictions, timeline, alerts, copilot, report, export."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import current_user, require
from ..demo.scenarios import ADMIN_AREAS, list_scenarios
from ..engines.change_detection import ChangeDetectionEngine
from ..engines.priority import DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS, normalise_weights
from ..engines.alerts import DEFAULT_ALERT_CONFIG
from ..models import (AOI, Alert, Event, FieldReport, H3Cell, HazardDetection, Infrastructure, IncidentTimeline, Notification, Prediction,
                      ProcessingJob, Resource, SatellitePass, Shelter)
from ..services import copilot, events as ev_svc, exports, pipeline, reports, summary
from ..services.common import audit, timeline
from ..services.twin import event_config, recompute
from ..core.config import get_settings
from .deps import get_event, need_analysis

router = APIRouter(prefix="/api", tags=["events"])
settings = get_settings()


class EventIn(BaseModel):
    name: str = Field(default="", max_length=200)
    hazard: str = "flood"
    aoi_method: str = "demo"  # draw|coordinates|admin|demo|upload
    aoi: dict = Field(default_factory=dict)
    scenario_key: str | None = None
    h3_resolution: int | None = Field(default=None, ge=6, le=10)
    start_date: datetime | None = None
    data_mode: str = Field(default="simulated", pattern="^(simulated|live)$")
    live: dict | None = None  # {pre_end, post_start, post_end, iso3?} for real-data events


class EventPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    severity: str | None = None
    status: str | None = None
    end_date: datetime | None = None


def event_out(db: Session, e: Event, detail: bool = False) -> dict:
    aoi = db.scalars(select(AOI).where(AOI.event_id == e.id)).first()
    job = db.scalars(select(ProcessingJob).where(ProcessingJob.event_id == e.id).order_by(ProcessingJob.id.desc())).first()
    out = {"id": e.id, "code": e.code, "name": e.name, "hazard": e.hazard, "scenario_key": e.scenario_key, "is_demo": e.is_demo,
           "start_date": e.start_date.isoformat(), "end_date": e.end_date.isoformat() if e.end_date else None, "severity": e.severity, "status": e.status,
           "h3_resolution": e.h3_resolution, "last_satellite_pass": e.last_satellite_pass.isoformat() if e.last_satellite_pass else None,
           "last_analysis": e.last_analysis.isoformat() if e.last_analysis else None, "assessment_version": e.assessment_version,
           "aoi": {"geometry": aoi.geom, "area_km2": round(aoi.area_km2, 1), "method": aoi.method, "name": aoi.name} if aoi else None,
           "job": {"id": job.id, "status": job.status, "progress": job.progress} if job else None,
           "label": "DEMONSTRATION DATA" if e.is_demo else "REAL DATA", "data_mode": (e.config or {}).get("world", {}).get("mode", "simulated")}
    if detail:
        out["data_freshness"] = summary.freshness(db, e)
        out["sensor_decision"] = e.config.get("sensor_decision")
    return out


@router.get("/scenarios")
def scenarios(_=Depends(current_user)):
    return {"scenarios": list_scenarios(), "admin_areas": ADMIN_AREAS}


@router.get("/events")
def list_events(include_archived: bool = False, db: Session = Depends(get_db), _=Depends(current_user)):
    q = select(Event).order_by(Event.id.desc())
    rows = db.scalars(q).all()
    return [event_out(db, e) for e in rows if include_archived or e.status != "archived"]


@router.post("/events", status_code=201)
def create_event(body: EventIn, db: Session = Depends(get_db), user=Depends(require("event.write"))):
    try:
        e = ev_svc.create_event(db, user, name=body.name, hazard=body.hazard, aoi_method=body.aoi_method, aoi_payload=body.aoi, scenario_key=body.scenario_key,
                                h3_resolution=body.h3_resolution, start_date=body.start_date, data_mode=body.data_mode, live=body.live)
    except (ValueError, KeyError) as ex:
        raise HTTPException(422, str(ex)) from ex
    db.commit()
    return event_out(db, e, True)


@router.get("/events/{event_id}")
def get_one(e: Event = Depends(get_event), db: Session = Depends(get_db), _=Depends(current_user)):
    return event_out(db, e, True)


@router.patch("/events/{event_id}")
def patch(body: EventPatch, e: Event = Depends(get_event), db: Session = Depends(get_db), user=Depends(require("event.write"))):
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(e, k, v)
    audit(db, user, "event.update", e.code, e.id, detail=body.model_dump(exclude_none=True, mode="json"))
    db.commit()
    return event_out(db, e, True)


@router.post("/events/{event_id}/archive")
def archive(e: Event = Depends(get_event), db: Session = Depends(get_db), user=Depends(require("event.write"))):
    e.status = "archived"
    audit(db, user, "event.archive", e.code, e.id)
    timeline(db, e.id, "status", "Event archived")
    db.commit()
    return event_out(db, e)


@router.post("/events/{event_id}/process", status_code=202)
def process(bg: BackgroundTasks, pace: bool = False, e: Event = Depends(get_event), db: Session = Depends(get_db), user=Depends(require("event.process"))):
    running = db.scalars(select(ProcessingJob).where(ProcessingJob.event_id == e.id, ProcessingJob.status.in_(["queued", "running"]))).first()
    if running:
        raise HTTPException(409, f"Analysis already running (job {running.id})")
    job = pipeline.start_job(db, e)
    audit(db, user, "event.process", e.code, e.id, detail={"job": job.id})
    db.commit()
    bg.add_task(pipeline.run_analysis, e.id, job.id, settings.demo_step_delay if pace else 0.0)
    return {"job_id": job.id, "status": job.status}


@router.post("/events/{event_id}/new-pass", status_code=202)
def new_pass(bg: BackgroundTasks, pace: bool = False, e: Event = Depends(need_analysis), db: Session = Depends(get_db), user=Depends(require("event.process"))):
    """Simulate a subsequent satellite pass: hazard has progressed; history is kept so escalations are detected."""
    running = db.scalars(select(ProcessingJob).where(ProcessingJob.event_id == e.id, ProcessingJob.status.in_(["queued", "running"]))).first()
    if running:
        raise HTTPException(409, f"Analysis already running (job {running.id})")
    if e.config["world"].get("mode") == "live":
        raise HTTPException(409, "A simulated 'new pass' is only available for demonstration events. For real-data events, create a new event with a later post-event window.")
    w = dict(e.config["world"])
    w["params"] = {**w["params"], "progress": int(w["params"].get("progress", 0)) + 1}
    e.config = {**e.config, "world": w}
    job = pipeline.start_job(db, e)
    audit(db, user, "event.new_pass", e.code, e.id, detail={"progress": w["params"]["progress"]})
    db.commit()
    bg.add_task(pipeline.run_analysis, e.id, job.id, settings.demo_step_delay if pace else 0.0, True)
    return {"job_id": job.id, "status": job.status}


@router.get("/events/{event_id}/status")
def status(e: Event = Depends(get_event), db: Session = Depends(get_db), _=Depends(current_user)):
    job = db.scalars(select(ProcessingJob).where(ProcessingJob.event_id == e.id).order_by(ProcessingJob.id.desc())).first()
    steps = job.steps if job else [{"key": k, "label": l, "status": "pending", "detail": ""} for k, l in pipeline.STEPS]
    from ..models import ResourceAssignment
    steps = [dict(s) for s in steps]
    if e.assessment_version:
        for s in steps:
            if s["key"] == "DISPATCH":
                n = db.query(ResourceAssignment).filter(ResourceAssignment.event_id == e.id, ResourceAssignment.status == "dispatched").count()
                s["status"], s["detail"] = ("done", f"{n} units dispatched") if n else ("awaiting", "No units dispatched yet")
            if s["key"] == "VERIFY":
                n = db.query(FieldReport).filter(FieldReport.event_id == e.id).count()
                s["status"], s["detail"] = ("done", f"{n} field report(s)") if n else ("awaiting", "No field verification yet")
    return {"event": event_out(db, e), "job": None if not job else {"id": job.id, "status": job.status, "progress": job.progress, "current_step": job.current_step, "error": job.error},
            "steps": steps}


@router.get("/events/{event_id}/kpis")
def kpis(e: Event = Depends(get_event), db: Session = Depends(get_db), _=Depends(current_user)):
    return summary.kpis(db, e)


@router.get("/command-center")
def command_center(db: Session = Depends(get_db), _=Depends(current_user)):
    events = [e for e in db.scalars(select(Event).order_by(Event.id.desc())).all() if e.status != "archived"]
    rows = []
    for e in events:
        rows.append({"event": event_out(db, e), "kpis": summary.kpis(db, e) if e.assessment_version else None})
    active = [r for r in rows if r["kpis"]]
    return {"events": rows, "totals": {"active_events": len(events), "p1": sum(r["kpis"]["levels"]["P1"] for r in active), "p2": sum(r["kpis"]["levels"]["P2"] for r in active),
                                       "people_at_risk": sum(r["kpis"]["people_at_risk"] for r in active)}}


# ----------------------------------------------------------------------------- map & cells


def _cell_feature(c: H3Cell, t: int, pred: Prediction | None) -> dict:
    p = {"h3_index": c.h3_index, "cell_no": c.cell_no, "priority_level": c.priority_level, "priority_score": c.priority_score, "severity": round(c.severity, 3),
         "confidence": c.confidence, "confidence_label": c.confidence_label, "population": c.population, "population_exposed": c.population_exposed,
         "vulnerability_score": c.vulnerability_score, "infrastructure_score": c.infrastructure_score, "road_status": c.road_status, "access_loss": c.access_loss,
         "risk": c.risk, "field_status": c.field_status, "affected_area_km2": round(c.affected_area_km2, 3), "cascade_risk": c.cascade_risk,
         "display_level": c.priority_level, "display_score": c.priority_score, "display_severity": round(c.severity, 3), "probability": None,
         "hospital": (c.components.get("facility_counts") or {}).get("hospital", 0), "school": (c.components.get("facility_counts") or {}).get("school", 0)}
    if t == -1:
        p.update(display_level="P4", display_score=0.0, display_severity=0.0)
    elif t > 0 and pred is not None:
        p.update(display_level=pred.predicted_level, display_score=pred.predicted_score, display_severity=pred.predicted_severity, probability=pred.expansion_probability)
    return {"type": "Feature", "id": c.h3_index, "geometry": c.geom, "properties": p}


@router.get("/events/{event_id}/map")
def map_data(t: int = Query(0, description="-1 before event, 0 now, or 6/12/24/48 h predicted"), e: Event = Depends(get_event), db: Session = Depends(get_db), _=Depends(current_user)):
    if t not in (-1, 0, 6, 12, 24, 48):
        raise HTTPException(422, "t must be one of -1, 0, 6, 12, 24, 48")
    aoi = db.scalars(select(AOI).where(AOI.event_id == e.id)).first()
    layers = []
    if e.assessment_version:
        sim = " (SIMULATED)" if e.is_demo else ""
        for name, label in (("sar_post", f"Satellite (SAR post-event){sim}"), ("sar_pre", f"Satellite (SAR pre-event){sim}"), ("hazard", f"{e.hazard.title()} detection"),
                            ("confidence", "Detection confidence"), ("population", f"Population{sim if sim else ' (modelled)'}")):
            layers.append({"key": name, "label": label})
        if (e.config or {}).get("has_rgb"):
            layers.append({"key": "optical", "label": "Sentinel-2 true colour"})
    cells = db.scalars(select(H3Cell).where(H3Cell.event_id == e.id).order_by(H3Cell.cell_no)).all()
    preds = {}
    if t > 0:
        preds = {p.h3_index: p for p in db.scalars(select(Prediction).where(Prediction.event_id == e.id, Prediction.horizon_h == t))}
    infra = db.scalars(select(Infrastructure).where(Infrastructure.event_id == e.id)).all()
    shelters = db.scalars(select(Shelter).where(Shelter.event_id == e.id)).all()
    res = db.scalars(select(Resource).where(Resource.event_id == e.id)).all()
    disp = ["P1", "P2", "P3", "P4"]
    feats = [_cell_feature(c, t, preds.get(c.h3_index)) for c in cells]
    counts = {k: sum(1 for f in feats if f["properties"]["display_level"] == k) for k in disp}
    return {"event": event_out(db, e), "time": t, "bounds": list(__import__("shapely.geometry", fromlist=["shape"]).shape(aoi.geom).bounds) if aoi else None,
            "aoi": aoi.geom if aoi else None, "layers": layers, "counts": counts,
            "cells": {"type": "FeatureCollection", "features": feats}, "roads": exports.road_geojson(db, e.id),
            "infrastructure": {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": i.geom, "properties": {"kind": i.kind, "name": i.name, "status": i.status, "risk": i.risk, "reason": i.risk_reason}} for i in infra]},
            "shelters": {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": s.geom, "properties": {"name": s.name, "capacity": s.capacity, "occupied": s.occupied, "in_hazard_zone": s.in_hazard_zone}} for s in shelters]},
            "resources": {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [r.lon, r.lat]}, "properties": {"kind": r.kind, "name": r.name, "status": r.status, "assigned_cell": r.assigned_cell}} for r in res]},
            "label": "DEMONSTRATION DATA" if e.is_demo else "REAL DATA", "data_mode": (e.config or {}).get("world", {}).get("mode", "simulated")}


@router.get("/events/{event_id}/layers/{layer}.png")
def layer(layer: str, e: Event = Depends(get_event), _=Depends(current_user)):
    try:
        png, bounds = exports.layer_png(e, layer)
    except FileNotFoundError:
        raise HTTPException(404, "Layer not available - run analysis first")
    except KeyError:
        raise HTTPException(404, f"Unknown layer '{layer}'")
    return Response(png, media_type="image/png", headers={"X-Layer-Bounds": ",".join(f"{b:.6f}" for b in bounds), "Cache-Control": "private, max-age=30", "Access-Control-Expose-Headers": "X-Layer-Bounds"})


@router.get("/events/{event_id}/layers")
def layer_info(e: Event = Depends(get_event), _=Depends(current_user)):
    try:
        _png, b = exports.layer_png(e, "hazard")
    except FileNotFoundError:
        return {"bounds": None}
    return {"bounds": b}


@router.get("/events/{event_id}/cells/{h3_index}")
def cell_detail(h3_index: str, e: Event = Depends(get_event), db: Session = Depends(get_db), _=Depends(current_user)):
    c = db.scalars(select(H3Cell).where(H3Cell.event_id == e.id, H3Cell.h3_index == h3_index)).first()
    if not c:
        raise HTTPException(404, "Cell not found")
    preds = db.scalars(select(Prediction).where(Prediction.event_id == e.id, Prediction.h3_index == h3_index).order_by(Prediction.horizon_h)).all()
    infra = db.scalars(select(Infrastructure).where(Infrastructure.event_id == e.id, Infrastructure.h3_index == h3_index)).all()
    reports_ = db.scalars(select(FieldReport).where(FieldReport.event_id == e.id, FieldReport.h3_index == h3_index).order_by(FieldReport.created_at.desc())).all()
    comp = c.components.get("priority", {})
    cfg = event_config(e)
    return {
        "h3_index": c.h3_index, "cell_no": c.cell_no, "lat": c.lat, "lon": c.lon, "priority": {"level": c.priority_level, "score": c.priority_score, "components": comp,
                                                                                                 "contributions": c.components.get("contributions", {}), "weights": normalise_weights(cfg["weights"])},
        "why": {"top_factors": [r["label"] for r in c.reason_codes[:4]], "reason_codes": c.reason_codes, "components_pct": {k: round(v * 100) for k, v in comp.items()}},
        "confidence": {"overall": c.confidence, "label": c.confidence_label, "detection": c.detection_confidence, "sources": c.sources},
        "hazard": {"severity": c.severity, "fraction": c.hazard_fraction, "affected_area_km2": c.affected_area_km2, "elevation_m": c.elevation_m, "slope_deg": c.slope_deg},
        "population": {"total": c.population, "exposed": c.population_exposed, "high_risk": c.population_high_risk, "isolated": c.population_isolated, "vulnerable": c.vulnerable_population,
                       "buildings": c.buildings, "estimated": True, "note": c.components.get("population_note")},
        "vulnerability": {"score": c.vulnerability_score, **(c.components.get("vulnerability") or {})},
        "infrastructure": {"score": c.infrastructure_score, "count": c.critical_facility_count, "items": [{"kind": i.kind, "name": i.name, "status": i.status, "risk": i.risk, "reason": i.risk_reason} for i in infra],
                           "counts": c.components.get("facility_counts", {})},
        "roads": {"status": c.road_status, "access_loss": c.access_loss, "nearest_shelter_km": c.nearest_shelter_km},
        "cascade": {"risk": c.cascade_risk, "reason": c.cascade_reason, "dependencies": c.affected_dependencies},
        "predictions": [{"horizon_h": p.horizon_h, "level": p.predicted_level, "probability": p.expansion_probability, "score": p.predicted_score, "confidence": p.confidence,
                         "confidence_label": p.confidence_label, "drivers": p.drivers, "label": "ESTIMATE"} for p in preds],
        "recommended_action": c.recommended_action, "field_status": c.field_status, "field_note": c.components.get("field_note", ""),
        "field_reports": [{"id": r.id, "verdict": r.verdict, "notes": r.notes, "at": r.created_at.isoformat(), "simulated": r.is_simulated, "effect": r.effect} for r in reports_],
        "assessment_version": e.assessment_version, "disclaimer": "DEMO / SIMULATED DATA" if e.is_demo else "",
    }


# ----------------------------------------------------------------------------- detections / priorities / predictions


@router.get("/events/{event_id}/detections")
def detections(e: Event = Depends(get_event), db: Session = Depends(get_db), _=Depends(current_user)):
    rows = db.scalars(select(HazardDetection).where(HazardDetection.event_id == e.id).order_by(HazardDetection.id.desc())).all()
    passes = db.scalars(select(SatellitePass).where(SatellitePass.event_id == e.id)).all()
    return {"detections": [{"id": d.id, "hazard": d.hazard, "model_name": d.model_name, "model_version": d.model_version, "sensor_mode": d.sensor_mode,
                            "sensor_explanation": d.sensor_explanation, "area_km2": d.detected_area_km2, "mean_confidence": d.mean_confidence, "mean_severity": d.mean_severity,
                            "outputs": d.outputs, "stats": d.stats, "footprint": d.footprint, "simulated_input": d.is_simulated_input, "created_at": d.created_at.isoformat()} for d in rows],
            "passes": [{"sensor": p.sensor, "phase": p.phase, "acquired_at": p.acquired_at.isoformat(), "cloud_cover_pct": p.cloud_cover_pct, "simulated": p.is_simulated, "source": p.source} for p in passes],
            "detectors": ChangeDetectionEngine().availability(e.hazard), "sensor_decision": e.config.get("sensor_decision"), "data_health": summary.data_health(db, e) if rows else None}


@router.get("/events/{event_id}/priorities")
def priorities(level: str | None = None, min_score: float = 0.0, q: str | None = None, limit: int = 500, e: Event = Depends(get_event),
               db: Session = Depends(get_db), _=Depends(current_user)):
    stmt = select(H3Cell).where(H3Cell.event_id == e.id, H3Cell.priority_score >= min_score)
    if level:
        stmt = stmt.where(H3Cell.priority_level.in_([x.strip().upper() for x in level.split(",")]))
    cells = db.scalars(stmt.order_by(H3Cell.priority_score.desc()).limit(limit)).all()
    if q:
        cells = [c for c in cells if q.lower() in str(c.cell_no) or q.lower() in " ".join(r["label"].lower() for r in c.reason_codes)]
    cfg = event_config(e)
    return {"weights": normalise_weights(cfg["weights"]), "thresholds": cfg["thresholds"], "default_weights": DEFAULT_WEIGHTS, "default_thresholds": DEFAULT_THRESHOLDS,
            "counts": {k: db.query(H3Cell).filter(H3Cell.event_id == e.id, H3Cell.priority_level == k).count() for k in ("P1", "P2", "P3", "P4")},
            "cells": [{"h3_index": c.h3_index, "cell_no": c.cell_no, "level": c.priority_level, "score": c.priority_score, "confidence": c.confidence, "confidence_label": c.confidence_label,
                       "components": c.components.get("priority", {}), "reason_codes": [r["label"] for r in c.reason_codes], "population_exposed": c.population_exposed,
                       "road_status": c.road_status, "recommended_action": c.recommended_action, "field_status": c.field_status, "severity": c.severity} for c in cells]}


class PriorityConfig(BaseModel):
    weights: dict[str, float] | None = None
    thresholds: dict[str, float] | None = None


@router.put("/events/{event_id}/priorities/config")
def priority_config(body: PriorityConfig, e: Event = Depends(need_analysis), db: Session = Depends(get_db), user=Depends(require("priority.configure"))):
    cfg = dict(e.config or {})
    if body.weights is not None:
        if any(k not in DEFAULT_WEIGHTS for k in body.weights) or any(v < 0 for v in body.weights.values()):
            raise HTTPException(422, f"weights keys must be {list(DEFAULT_WEIGHTS)} with non-negative values")
        cfg["weights"] = body.weights
    if body.thresholds is not None:
        t = {**DEFAULT_THRESHOLDS, **body.thresholds}
        if not (t["P1"] > t["P2"] > t["P3"] >= 0):
            raise HTTPException(422, "thresholds must satisfy P1 > P2 > P3 >= 0")
        cfg["thresholds"] = t
    e.config = cfg
    audit(db, user, "priority.configure", e.code, e.id, reason="Weights/thresholds changed", detail=body.model_dump())
    out = recompute(db, e, trigger="config", user=user)
    timeline(db, e.id, "priority", "Priority configuration changed - recalculated", str(body.model_dump()))
    db.commit()
    return {"ok": True, "version": out["version"], "summary": out["summary"]}


@router.get("/events/{event_id}/predictions")
def predictions(e: Event = Depends(need_analysis), db: Session = Depends(get_db), _=Depends(current_user)):
    cells = {c.h3_index: c for c in summary.cells_of(db, e.id)}
    rows = db.scalars(select(Prediction).where(Prediction.event_id == e.id)).all()
    by_h: dict[int, list[Prediction]] = {}
    for r in rows:
        by_h.setdefault(r.horizon_h, []).append(r)
    cur = {k: sum(1 for c in cells.values() if c.priority_level == k) for k in ("P1", "P2", "P3", "P4")}
    horizons = []
    for h in sorted(by_h):
        rs = by_h[h]
        counts = {k: sum(1 for r in rs if r.predicted_level == k) for k in ("P1", "P2", "P3", "P4")}
        esc = sorted([r for r in rs if r.predicted_level != r.current_level and ["P1", "P2", "P3", "P4"].index(r.predicted_level) < ["P1", "P2", "P3", "P4"].index(r.current_level)],
                     key=lambda r: -r.expansion_probability)
        horizons.append({"horizon_h": h, "counts": counts, "escalating_count": len(esc), "p1_new": sum(1 for r in esc if r.predicted_level == "P1"),
                         "escalations": [{"h3_index": r.h3_index, "cell_no": cells[r.h3_index].cell_no, "current": r.current_level, "predicted": r.predicted_level, "probability": r.expansion_probability,
                                          "confidence_label": r.confidence_label, "drivers": r.drivers} for r in esc[:40]]})
    first = rows[0] if rows else None
    return {"current": cur, "horizons": horizons, "model": {"name": first.model_name, "version": first.model_version} if first else None, "weather": e.config.get("weather"),
            "label": "ESTIMATES - heuristic risk-propagation model (uncalibrated). Not guaranteed outcomes."}


# ----------------------------------------------------------------------------- timeline, alerts, intelligence


@router.get("/events/{event_id}/timeline")
def get_timeline(e: Event = Depends(get_event), db: Session = Depends(get_db), _=Depends(current_user)):
    rows = db.scalars(select(IncidentTimeline).where(IncidentTimeline.event_id == e.id).order_by(IncidentTimeline.at, IncidentTimeline.id)).all()
    return [{"id": r.id, "at": r.at.isoformat(), "kind": r.kind, "title": r.title, "detail": r.detail, "h3_index": r.h3_index} for r in rows]


@router.get("/events/{event_id}/alerts")
def get_alerts(e: Event = Depends(get_event), db: Session = Depends(get_db), _=Depends(current_user)):
    rows = db.scalars(select(Alert).where(Alert.event_id == e.id).order_by(Alert.id.desc()).limit(200)).all()
    notes = db.scalars(select(Notification).where(Notification.event_id == e.id).order_by(Notification.id.desc()).limit(200)).all()
    cfg = event_config(e)["alerts"]
    return {"alerts": [{"id": a.id, "trigger": a.trigger, "severity": a.severity, "title": a.title, "detail": a.detail, "h3_index": a.h3_index, "acknowledged": a.acknowledged,
                        "at": a.created_at.isoformat()} for a in rows],
            "notifications": [{"id": n.id, "alert_id": n.alert_id, "channel": n.channel, "recipient": n.recipient, "status": n.status, "provider": n.provider, "at": n.created_at.isoformat()} for n in notes],
            "config": cfg, "provider": settings.notify_provider, "note": "Demo mode: notifications are recorded as MOCK_SENT and never leave this system." if settings.notify_provider == "mock" else ""}


@router.post("/events/{event_id}/alerts/{alert_id}/ack")
def ack(alert_id: int, e: Event = Depends(get_event), db: Session = Depends(get_db), user=Depends(require("resource.assign"))):
    a = db.get(Alert, alert_id)
    if not a or a.event_id != e.id:
        raise HTTPException(404, "Alert not found")
    a.acknowledged = True
    audit(db, user, "alert.ack", a.title, e.id)
    db.commit()
    return {"ok": True}


@router.put("/events/{event_id}/alerts/config")
def alert_config(body: dict, e: Event = Depends(get_event), db: Session = Depends(get_db), user=Depends(require("priority.configure"))):
    merged = {}
    for k, v in body.items():
        if k not in DEFAULT_ALERT_CONFIG or not isinstance(v, dict):
            raise HTTPException(422, f"Unknown alert trigger '{k}'")
        ch = v.get("channels", DEFAULT_ALERT_CONFIG[k]["channels"])
        if any(c not in ("dashboard", "email", "sms", "whatsapp") for c in ch):
            raise HTTPException(422, "Unknown channel")
        merged[k] = {**DEFAULT_ALERT_CONFIG[k], **v}
    e.config = {**e.config, "alerts": {**e.config.get("alerts", {}), **merged}}
    audit(db, user, "alert.configure", e.code, e.id, detail=merged)
    db.commit()
    return {"config": event_config(e)["alerts"]}


@router.get("/events/{event_id}/what-changed")
def what_changed(frm: int | None = None, to: int | None = None, e: Event = Depends(need_analysis), db: Session = Depends(get_db), _=Depends(current_user)):
    return summary.what_changed(db, e, frm, to)


@router.get("/events/{event_id}/recommendations")
def recs(e: Event = Depends(get_event), db: Session = Depends(get_db), _=Depends(current_user)):
    return {"actions": summary.recommendations(db, e), "note": "Every action cites system data; AI assists decisions and does not replace commander judgement."}


@router.get("/events/{event_id}/summary")
def exec_summary(e: Event = Depends(get_event), db: Session = Depends(get_db), _=Depends(current_user)):
    return summary.exec_summary(db, e)


@router.get("/events/{event_id}/data-health")
def data_health(e: Event = Depends(get_event), db: Session = Depends(get_db), _=Depends(current_user)):
    return summary.data_health(db, e)


@router.get("/events/{event_id}/evaluation")
def evaluation(e: Event = Depends(get_event), db: Session = Depends(get_db), _=Depends(current_user)):
    gt = (e.config or {}).get("evaluation")
    if gt:
        return {"available": True, **gt}
    if e.is_demo:
        return {"available": False, "message": "Evaluation metrics unavailable for synthetic demonstration data.",
                "metrics": {k: None for k in ("accuracy", "precision", "recall", "f1", "iou", "false_positive_rate")}}
    return {"available": False, "message": "No ground-truth reference has been registered for this event.", "metrics": {}}


class GroundTruth(BaseModel):
    geojson: dict


@router.post("/events/{event_id}/evaluation")
def register_ground_truth(body: GroundTruth, e: Event = Depends(need_analysis), db: Session = Depends(get_db), user=Depends(require("data.manage"))):
    if e.is_demo:
        raise HTTPException(409, "Evaluation metrics unavailable for synthetic demonstration data.")
    from ..engines.evaluation import evaluate_event
    res = evaluate_event(e, body.geojson)
    e.config = {**e.config, "evaluation": res}
    audit(db, user, "evaluation.register", e.code, e.id)
    db.commit()
    return {"available": True, **res}


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)


@router.post("/events/{event_id}/copilot")
def ask(body: AskIn, e: Event = Depends(get_event), db: Session = Depends(get_db), user=Depends(current_user)):
    out = copilot.ask(db, e, body.question)
    audit(db, user, "copilot.ask", body.question[:120], e.id, detail={"intent": out["intent"]})
    db.commit()
    return out


@router.get("/events/{event_id}/report")
def report(e: Event = Depends(need_analysis), db: Session = Depends(get_db), user=Depends(require("report.generate"))):
    pdf = reports.build_pdf(db, e, user)
    audit(db, user, "report.generate", e.code, e.id)
    timeline(db, e.id, "report", "Situation report generated")
    db.commit()
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="DISHA_{e.code}_situation_report.pdf"'})


@router.get("/events/{event_id}/export")
def export(format: str = Query("geojson"), layer: str = "severity", e: Event = Depends(need_analysis), db: Session = Depends(get_db), user=Depends(require("view"))):
    f = format.lower()
    audit(db, user, "export", f"{e.code}.{f}", e.id)
    db.commit()
    if f == "geojson":
        return JSONResponse(exports.geojson(db, e), media_type="application/geo+json", headers={"Content-Disposition": f'attachment; filename="{e.code}.geojson"'})
    if f == "csv":
        return Response(exports.csv_text(db, e), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{e.code}.csv"'})
    if f == "kml":
        return Response(exports.kml_text(db, e), media_type="application/vnd.google-earth.kml+xml", headers={"Content-Disposition": f'attachment; filename="{e.code}.kml"'})
    if f == "pdf":
        return Response(reports.build_pdf(db, e, user), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{e.code}.pdf"'})
    if f == "cog":
        try:
            return Response(exports.cog_bytes(e, layer), media_type="image/tiff", headers={"Content-Disposition": f'attachment; filename="{e.code}_{layer}.tif"'})
        except ImportError:
            raise HTTPException(501, "COG export needs rasterio (pip install rasterio)")
        except FileNotFoundError as ex:
            raise HTTPException(404, str(ex))
    raise HTTPException(422, "format must be geojson|kml|csv|pdf|cog")
