"""Digital twin service: event config, cell state, field-effect application, priority recompute, versioning."""
from __future__ import annotations

from datetime import datetime, timezone

import h3
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..engines import escalation, prediction
from ..engines.alerts import DEFAULT_ALERT_CONFIG, build_alerts
from ..engines.fusion import overall_confidence, source_status
from ..engines.priority import EXPOSURE_REF_FLOOR, DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS, PriorityInput, compute_priority, confidence_label
from ..models import (DataSource, Event, FieldReport, H3Cell, Infrastructure, Prediction, PriorityResult, RoadSegment)
from .common import now, persist_alerts, timeline


def event_config(event: Event) -> dict:
    c = event.config or {}
    return {
        "weights": {**DEFAULT_WEIGHTS, **c.get("weights", {})},
        "thresholds": {**DEFAULT_THRESHOLDS, **c.get("thresholds", {})},
        "vuln_weights": c.get("vuln_weights", {}),
        "alerts": {**DEFAULT_ALERT_CONFIG, **c.get("alerts", {})},
    }


def snapshot_of(c: H3Cell, level: str | None = None, blocked_segments: int = 0) -> dict:
    return {
        "level": level or c.priority_level, "score": c.priority_score, "severity": c.severity, "confidence": c.confidence,
        "access_loss": c.access_loss, "population_exposed": c.population_exposed, "population_high_risk": c.population_high_risk,
        "infrastructure_score": c.infrastructure_score, "field_status": c.field_status, "affected_area_km2": c.affected_area_km2,
        "hospitals": (c.components or {}).get("facility_counts", {}).get("hospital", 0), "blocked_segments": blocked_segments,
    }


def latest_reports(db: Session, event_id: int) -> dict[str, FieldReport]:
    rows = db.scalars(select(FieldReport).where(FieldReport.event_id == event_id).order_by(FieldReport.created_at)).all()
    return {r.h3_index: r for r in rows}


def field_effect(base_sev: float, base_conf: float, base_exp: int, pop: int, rep: FieldReport | None) -> dict:
    """Apply the latest field verdict to detection-derived values. Reversible: always starts from `base`."""
    if rep is None:
        return {"severity": base_sev, "confidence": base_conf, "exposed": base_exp, "status": "unverified", "note": ""}
    v = rep.verdict
    sev, conf, exp, note = base_sev, base_conf, base_exp, ""
    if v == "confirmed":
        conf = min(0.99, base_conf + 0.12)
        note = "Field responder confirmed detection (+0.12 confidence)."
    elif v == "severe":
        sev = max(base_sev, rep.observed_severity or 0.9)
        conf = min(0.99, base_conf + 0.15)
        exp = max(base_exp, int(0.6 * pop))
        note = "Field responder reported severe impact: severity raised; >=60% of residents assumed exposed until measured."
    elif v == "partially_affected":
        sev, conf = base_sev * 0.65, min(0.99, base_conf + 0.08)
        exp = int(base_exp * 0.65)
        note = "Partially affected per field report: severity and exposure scaled to 65%."
    elif v == "false_alarm":
        sev, conf = base_sev * 0.15, 0.9
        exp = int(base_exp * 0.15)
        note = "Field responder reported a false alarm: severity and exposure scaled to 15%; model feedback recorded."
    elif v == "resolved":
        note = "Marked resolved by field team."
    return {"severity": float(np.clip(sev, 0, 1)), "confidence": conf, "exposed": exp, "status": v if v != "partially_affected" else "partial", "note": note}


def _datasources(db: Session, event_id: int) -> dict[str, DataSource]:
    return {d.key: d for d in db.scalars(select(DataSource).where(DataSource.event_id == event_id)).all()}


def cell_sources(c: H3Cell, ds: dict[str, DataSource], rep: FieldReport | None, has_roads: bool, sat_quality: float) -> list[dict]:
    def mk(key, avail=True, q=0.85):
        d = ds.get(key)
        if d is None:
            return source_status(key, False, 0, None, 24, True)
        return source_status(key, avail and d.availability > 0, min(q, d.quality) if q else d.quality, d.last_updated, d.stale_after_hours, d.is_simulated)

    src = [mk("satellite", True, sat_quality), mk("weather"), mk("population"), mk("roads", has_roads), mk("infrastructure")]
    if rep:
        src.append(source_status("field", True, 0.95, rep.created_at, 24, rep.is_simulated))
    else:
        src.append(source_status("field", False, 0, None, 24, False))
    return src


def recompute(db: Session, event: Event, trigger: str = "analysis", user=None, predict: bool = True, announce: bool = True) -> dict:
    """Re-evaluate every cell from base detection values + field reports; version++; diff; alerts; predictions."""
    cfg = event_config(event)
    cells = db.scalars(select(H3Cell).where(H3Cell.event_id == event.id)).all()
    if not cells:
        return {"escalations": [], "version": event.assessment_version}
    reports = latest_reports(db, event.id)
    ds = _datasources(db, event.id)
    by = {c.h3_index: c for c in cells}
    prev_version = event.assessment_version
    prev = {}
    if prev_version:
        for r in db.scalars(select(PriorityResult).where(PriorityResult.event_id == event.id, PriorityResult.version == prev_version)):
            prev[r.h3_index] = {**r.snapshot, "level": r.level, "score": r.score, "confidence": r.confidence}
    prev_blocked = int(db.query(RoadSegment).filter(RoadSegment.event_id == event.id, RoadSegment.status == "blocked").count())

    # 1) effective state from base + field
    eff = {}
    for c in cells:
        base = c.components.get("base", {"severity": c.severity, "confidence": c.detection_confidence, "exposed": c.population_exposed})
        eff[c.h3_index] = field_effect(base["severity"], base["confidence"], base["exposed"], c.population, reports.get(c.h3_index))
    affected_exposed = [e["exposed"] for e in eff.values() if e["exposed"] > 0]
    exposure_ref = float(np.percentile(affected_exposed, 95)) if affected_exposed else 1.0
    exposure_ref = max(exposure_ref, EXPOSURE_REF_FLOOR)

    # 2) infra exposure from neighbours, then priority
    results = {}
    for c in cells:
        e = eff[c.h3_index]
        nb = [eff[n]["severity"] for n in h3.grid_ring(c.h3_index, 1) if n in eff]
        hazard_exp = max(e["severity"], 0.6 * (max(nb) if nb else 0.0))
        presence = c.components.get("infra_presence", 0.0)
        infra = presence * (0.2 + 0.8 * min(1.0, hazard_exp)) if hazard_exp > 0.02 else 0.0
        infra = min(1.0, infra + 0.35 * c.cascade_risk * (1 if hazard_exp > 0.02 or c.cascade_risk > 0.5 else 0))
        c.severity, c.detection_confidence, c.population_exposed = e["severity"], e["confidence"], e["exposed"]
        c.field_status = e["status"]
        c.infrastructure_score = round(infra, 4)
        counts = c.components.get("facility_counts", {})
        pi = PriorityInput(
            severity=e["severity"], confidence=e["confidence"], exposure_pop_norm=min(1.0, e["exposed"] / exposure_ref),
            vulnerability=c.vulnerability_score, infrastructure_score=infra, access_loss=c.access_loss,
            population_exposed=e["exposed"], vulnerable_population=int(c.vulnerable_population * (e["exposed"] / max(c.components.get("base", {}).get("exposed", 1), 1) if e["exposed"] else 0)) if c.components.get("base", {}).get("exposed") else c.vulnerable_population,
            hospitals=counts.get("hospital_near", 0), schools=counts.get("school", 0), power=counts.get("power", 0),
            critical_facility_count=c.critical_facility_count, road_status=c.road_status, isolated_population=c.population_isolated,
            cascade_risk=c.cascade_risk, field_status=e["status"], hazard=event.hazard,
        )
        out = compute_priority(pi, cfg["weights"], cfg["thresholds"])
        rep = reports.get(c.h3_index)
        sat_q = c.components.get("base", {}).get("confidence", 0.8) if c.hazard_fraction > 0 else 0.85
        srcs = cell_sources(c, ds, rep, c.components.get("road_m", 0) > 0, sat_q)
        fused, _ = overall_confidence(srcs)
        results[c.h3_index] = (out, fused, srcs, e)

    # 3) rank -> stable cell_no on first assessment
    if any(c.cell_no is None for c in cells):
        nxt = max([c.cell_no for c in cells if c.cell_no is not None] or [0]) + 1
        for c in sorted([c for c in cells if c.cell_no is None], key=lambda c: (-results[c.h3_index][0].score, c.h3_index)):
            c.cell_no, nxt = nxt, nxt + 1

    version = prev_version + 1
    cur = {}
    for c in cells:
        out, fused, srcs, e = results[c.h3_index]
        c.priority_score, c.priority_level = out.score, out.level
        c.confidence, c.confidence_label = fused, confidence_label(fused)
        c.components = {**c.components, "priority": out.components, "contributions": out.contributions, "field_note": e["note"]}
        c.reason_codes, c.recommended_action, c.sources = out.reason_codes, out.recommended_action, srcs
        c.risk = round(max(out.score, c.cascade_risk * 0.6), 3)
        c.updated_at = now()
        snap = snapshot_of(c, blocked_segments=0)
        cur[c.h3_index] = snap
        db.add(PriorityResult(event_id=event.id, h3_index=c.h3_index, version=version, score=out.score, level=out.level,
                              components=out.components, confidence=fused, reason_codes=out.reason_codes, snapshot=snap, trigger=trigger))
    event.assessment_version = version
    event.last_analysis = now()
    event.config = {**event.config, "road_hist": {**event.config.get("road_hist", {}), str(version): prev_blocked}}
    cell_no = {c.h3_index: c.cell_no for c in cells}
    esc = escalation.diff_priorities(prev, cur, cell_no) if prev else []
    cur_blocked = int(db.query(RoadSegment).filter(RoadSegment.event_id == event.id, RoadSegment.status == "blocked").count())
    db.flush()
    pred_info = {}
    if predict:
        pred_info = run_predictions(db, event, version)
    if announce:
        prev_sum = escalation.summarise(prev) if prev else None
        cur_sum = escalation.summarise(cur)
        hosp = [{"name": i.name, "reason": i.risk_reason, "h3_index": i.h3_index} for i in
                db.scalars(select(Infrastructure).where(Infrastructure.event_id == event.id, Infrastructure.kind == "hospital", Infrastructure.risk >= 0.25))]
        iso = [c.h3_index for c in cells if c.population_isolated > 0]
        ctx = {"isolated_cells": iso, "isolated_pop": sum(c.population_isolated for c in cells), "prev_isolated": event.config.get("prev_isolated", 0) if prev else 0,
               "hospitals_at_risk": hosp, "prev_hospitals": event.config.get("prev_hospitals", []) if prev else [],
               "predicted_p1_escalations": pred_info.get("p1_escalations_6h", 0)}
        sev_rep = next((r for h, r in reports.items() if r.verdict == "severe" and trigger == "field_report" and r.created_at and (now() - r.created_at.replace(tzinfo=timezone.utc)).total_seconds() < 120), None)
        if sev_rep:
            ctx["field_severe"] = {"cell_no": cell_no.get(sev_rep.h3_index), "h3_index": sev_rep.h3_index, "notes": sev_rep.notes}
        specs = build_alerts(cfg["alerts"], prev_sum, cur_sum, esc, ctx)
        persist_alerts(db, event, specs)
        event.config = {**event.config, "prev_isolated": len(iso), "prev_hospitals": [h["name"] for h in hosp]}
        for e in esc[:10]:
            timeline(db, event.id, "escalation", e["message"], "; ".join(e["reasons"]), e["h3_index"])
    return {"escalations": esc, "version": version, "summary": escalation.summarise(cur), "prev_summary": escalation.summarise(prev) if prev else None,
            "prev_blocked": prev_blocked, "cur_blocked": cur_blocked, "predictions": pred_info}


def run_predictions(db: Session, event: Event, version: int) -> dict:
    cfg = event_config(event)
    cells = db.scalars(select(H3Cell).where(H3Cell.event_id == event.id)).all()
    weather = (event.config or {}).get("weather", {})
    exposed = [c.population_exposed for c in cells if c.population_exposed > 0]
    ref = max(float(np.percentile(exposed, 95)) if exposed else 1.0, EXPOSURE_REF_FLOOR)
    dicts = [{
        "h3_index": c.h3_index, "severity": c.severity, "hazard_fraction": c.hazard_fraction, "elevation_m": c.elevation_m, "slope_deg": c.slope_deg,
        "confidence": c.detection_confidence, "population": c.population, "road_m": c.components.get("road_m", 0), "infra_presence": c.components.get("infra_presence", 0),
        "vulnerability_score": c.vulnerability_score, "access_loss": c.access_loss, "infrastructure_score": c.infrastructure_score,
        "priority_level": c.priority_level,
    } for c in cells]
    recs = prediction.predict(dicts, weather, event.hazard, cfg["weights"], cfg["thresholds"], ref)
    db.query(Prediction).filter(Prediction.event_id == event.id).delete()
    for r in recs:
        db.add(Prediction(event_id=event.id, version=version, model_name=prediction.MODEL_NAME, model_version=prediction.MODEL_VERSION, **{k: v for k, v in r.items() if k != "predicted_population_exposed"}))
    p1_6 = [r for r in recs if r["horizon_h"] == 6 and r["predicted_level"] == "P1" and r["current_level"] != "P1"]
    thr = cfg["alerts"]["prediction_threshold"].get("probability", 0.75)
    return {"p1_escalations_6h": len([r for r in p1_6 if r["expansion_probability"] >= min(thr, 0.5)]), "records": len(recs)}
