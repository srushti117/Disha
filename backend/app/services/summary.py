"""Read-side intelligence: KPIs, data health, executive summary, recommendations, what-changed. Every sentence is built from DB values."""
from __future__ import annotations

from datetime import timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..engines import escalation
from ..engines.priority import LEVEL_NAMES
from ..models import (DataSource, Event, FieldReport, H3Cell, HazardDetection, Infrastructure, Prediction, PriorityResult, Resource,
                      ResourceAssignment, RoadSegment, Shelter)
from . import response
from .common import now

DISCLAIMER = "DEMO / SIMULATED DATA - not live satellite, weather or government data."


def cells_of(db: Session, event_id: int) -> list[H3Cell]:
    return db.scalars(select(H3Cell).where(H3Cell.event_id == event_id)).all()


def kpis(db: Session, event: Event) -> dict:
    cells = cells_of(db, event.id)
    lv = {k: sum(1 for c in cells if c.priority_level == k) for k in ("P1", "P2", "P3", "P4")}
    infra = db.scalars(select(Infrastructure).where(Infrastructure.event_id == event.id)).all()
    risky = [i for i in infra if i.risk >= 0.25]
    roads = db.scalars(select(RoadSegment).where(RoadSegment.event_id == event.id)).all()
    rs = response.resource_summary(db, event.id)
    cov = (event.config or {}).get("coverage")
    return {
        "event_id": event.id, "assessment_version": event.assessment_version, "levels": lv,
        "affected_cells": sum(1 for c in cells if c.severity >= 0.03), "affected_area_km2": round(sum(c.affected_area_km2 for c in cells), 2),
        "people_at_risk": sum(c.population_high_risk for c in cells), "people_exposed": sum(c.population_exposed for c in cells),
        "people_isolated": sum(c.population_isolated for c in cells), "population_total": sum(c.population for c in cells),
        "critical_infrastructure": {"total": len(infra), "at_risk": len(risky),
                                    "by_kind": {k: sum(1 for i in risky if i.kind == k) for k in sorted({i.kind for i in infra})},
                                    "hospitals_at_risk": sum(1 for i in risky if i.kind == "hospital")},
        "roads": {"total": len(roads), "blocked": sum(r.status == "blocked" for r in roads), "potentially_blocked": sum(r.status == "potentially_blocked" for r in roads),
                  "unknown": sum(r.status == "unknown" for r in roads)},
        "resources": {"available": rs["available"], "deployed": rs["deployed"], "unassigned_p1": rs["unassigned_p1"], "p1_total": rs["p1_total"]},
        "resource_coverage": cov, "data_freshness": freshness(db, event), "disclaimer": DISCLAIMER if event.is_demo else "",
    }


def freshness(db: Session, event: Event) -> list[dict]:
    out = []
    tnow = now()
    for d in db.scalars(select(DataSource).where(DataSource.event_id == event.id)):
        lu = d.last_updated if d.last_updated.tzinfo else d.last_updated.replace(tzinfo=timezone.utc)
        age = (tnow - lu).total_seconds() / 3600
        out.append({"key": d.key, "name": d.name, "last_updated": lu.isoformat(), "age_hours": round(age, 1), "stale_after_hours": d.stale_after_hours,
                    "stale": age > d.stale_after_hours, "simulated": d.is_simulated, "quality": d.quality})
    last_field = db.scalars(select(FieldReport).where(FieldReport.event_id == event.id).order_by(FieldReport.created_at.desc())).first()
    if last_field:
        lu = last_field.created_at if last_field.created_at.tzinfo else last_field.created_at.replace(tzinfo=timezone.utc)
        out.append({"key": "field", "name": "Field reports", "last_updated": lu.isoformat(), "age_hours": round((tnow - lu).total_seconds() / 3600, 1),
                    "stale_after_hours": 24, "stale": False, "simulated": last_field.is_simulated, "quality": 0.95})
    return out


def data_health(db: Session, event: Event) -> dict:
    det = db.scalars(select(HazardDetection).where(HazardDetection.event_id == event.id).order_by(HazardDetection.id.desc())).first()
    ds = {d.key: d for d in db.scalars(select(DataSource).where(DataSource.event_id == event.id))}
    n_field = db.query(FieldReport).filter(FieldReport.event_id == event.id).count()
    cloud = (event.config or {}).get("sensor_decision", {}).get("cloud_cover_pct")
    label = lambda q: "Good" if q >= 0.75 else "Fair" if q >= 0.55 else "Poor"  # noqa: E731
    return {
        "satellite_availability_pct": round(100 * ds["satellite"].availability * ds["satellite"].quality, 0) if "satellite" in ds else None,
        "cloud_quality_pct": None if cloud is None else round(100 - cloud, 0), "cloud_cover_pct": cloud,
        "sensor_mode": det.sensor_mode if det else None, "sensor_explanation": det.sensor_explanation if det else None,
        "population": label(ds["population"].quality) if "population" in ds else "Unavailable", "roads": label(ds["roads"].quality) if "roads" in ds else "Unavailable",
        "weather": label(ds["weather"].quality) if "weather" in ds else "Unavailable", "infrastructure": label(ds["infrastructure"].quality) if "infrastructure" in ds else "Unavailable",
        "field_observations": n_field, "freshness": freshness(db, event), "simulated": any(d.is_simulated for d in ds.values()) if ds else None,
        "stale_layers": [f["name"] for f in freshness(db, event) if f["stale"]],
    }


def exec_summary(db: Session, event: Event) -> dict:
    k = kpis(db, event)
    if not event.assessment_version:
        return {"text": "No analysis has been run for this event yet.", "facts": {}}
    cells = sorted(cells_of(db, event.id), key=lambda c: c.cell_no or 9999)
    p1 = [c for c in cells if c.priority_level == "P1"]
    lv = k["levels"]
    det = db.scalars(select(HazardDetection).where(HazardDetection.event_id == event.id).order_by(HazardDetection.id.desc())).first()
    parts = [f"Current analysis (assessment v{event.assessment_version}) identifies {lv['P1']} P1 and {lv['P2']} P2 cells across the affected region "
             f"({k['affected_area_km2']:.1f} km2 affected, {det.sensor_mode if det else 'n/a'} sensor mode)."]
    if p1:
        t = p1[0]
        parts.append(f"The highest-priority location, Cell {t.cell_no:02d}, scores {t.priority_score:.2f}: " + "; ".join(r["label"].lower() for r in t.reason_codes[:3]) + ".")
    parts.append(f"{k['people_at_risk']:,} people are at high risk and {k['people_exposed']:,} are exposed; {k['people_isolated']:,} are potentially isolated by blocked roads.")
    ci = k["critical_infrastructure"]
    parts.append(f"{ci['at_risk']} critical facilities are at risk, including {ci['hospitals_at_risk']} hospital(s).")
    r = k["roads"]
    parts.append(f"{r['blocked']} road segments are blocked and {r['potentially_blocked']} potentially blocked.")
    p6 = db.query(Prediction).filter(Prediction.event_id == event.id, Prediction.horizon_h == 6, Prediction.predicted_level == "P1", Prediction.current_level != "P1").count()
    if p6:
        parts.append(f"Estimate: {p6} additional location(s) may escalate to P1 within 6 hours (heuristic model, not guaranteed).")
    n_field = db.query(FieldReport).filter(FieldReport.event_id == event.id).count()
    parts.append(f"{n_field} field report(s) received." if n_field else "No field verification yet.")
    return {"text": " ".join(parts), "facts": {"levels": lv, "people_at_risk": k["people_at_risk"], "version": event.assessment_version},
            "generated_at": now().isoformat(), "disclaimer": DISCLAIMER if event.is_demo else ""}


def top_cells(db: Session, event: Event, level="P1", limit=20) -> list[H3Cell]:
    return db.scalars(select(H3Cell).where(H3Cell.event_id == event.id, H3Cell.priority_level == level).order_by(H3Cell.priority_score.desc()).limit(limit)).all()


def recommendations(db: Session, event: Event, limit: int = 8) -> list[dict]:
    if not event.assessment_version:
        return []
    out: list[dict] = []
    cells = cells_of(db, event.id)
    cell_by = {c.h3_index: c for c in cells}
    assigned = {}
    for a in db.scalars(select(ResourceAssignment).where(ResourceAssignment.event_id == event.id, ResourceAssignment.status.in_(["recommended", "dispatched"]))):
        assigned.setdefault(a.h3_index, []).append(a)
    p1 = sorted([c for c in cells if c.priority_level == "P1"], key=lambda c: -c.priority_score)
    for c in p1[:3]:
        have = [a.resource.name for a in assigned.get(c.h3_index, []) if a.resource.kind == "rescue_team"]
        team = have[0] if have else "a rescue team"
        out.append({"action": f"Deploy {team} to Cell {c.cell_no:02d}", "why": [r["label"] for r in c.reason_codes[:4]], "cell_no": c.cell_no, "h3_index": c.h3_index,
                    "kind": "deploy", "data": {"priority_score": c.priority_score, "population_exposed": c.population_exposed, "confidence": c.confidence}})
    for c in [c for c in p1 if c.access_loss >= 0.5][:2]:
        out.append({"action": f"Establish alternate route to Cell {c.cell_no:02d}", "why": [f"Road access loss {c.access_loss:.0%} ({c.road_status.replace('_', ' ')})"] +
                    ([f"{c.population_isolated:,} people potentially isolated"] if c.population_isolated else []), "cell_no": c.cell_no, "h3_index": c.h3_index, "kind": "route",
                    "data": {"access_loss": c.access_loss}})
    hosp = db.scalars(select(Infrastructure).where(Infrastructure.event_id == event.id, Infrastructure.kind == "hospital", Infrastructure.risk >= 0.25).order_by(Infrastructure.risk.desc())).all()
    for h in hosp[:2]:
        c = cell_by.get(h.h3_index)
        out.append({"action": f"Check {h.name}" + (f" near Cell {c.cell_no:02d}" if c else ""), "why": [h.risk_reason or "Exposed to hazard", f"Risk {h.risk:.0%} ({h.status})"],
                    "cell_no": c.cell_no if c else None, "h3_index": h.h3_index, "kind": "hospital", "data": {"risk": h.risk}})
    preds = db.scalars(select(Prediction).where(Prediction.event_id == event.id, Prediction.horizon_h == 6, Prediction.predicted_level.in_(["P1", "P2"]),
                                                Prediction.current_level.in_(["P2", "P3", "P4"]))).all()
    esc = sorted([p for p in preds if p.predicted_level == "P1" and p.current_level != "P1"], key=lambda p: -p.expansion_probability)
    for p in esc[:2]:
        c = cell_by.get(p.h3_index)
        if c and c.vulnerable_population >= 100:
            out.append({"action": f"Evacuate vulnerable population from Cell {c.cell_no:02d}", "why": [f"{c.vulnerable_population:,} vulnerable people (estimated)",
                        f"Estimated {p.expansion_probability:.0%} probability of escalation to P1 within 6 h", *p.drivers[:1]], "cell_no": c.cell_no, "h3_index": c.h3_index,
                        "kind": "evacuate", "data": {"probability": p.expansion_probability}})
    for p in esc[2:4]:
        c = cell_by.get(p.h3_index)
        if c:
            out.append({"action": f"Monitor Cell {c.cell_no:02d}", "why": [f"Currently {p.current_level}; estimated {p.expansion_probability:.0%} chance of P1 within 6 h"], "cell_no": c.cell_no,
                        "h3_index": c.h3_index, "kind": "monitor", "data": {"probability": p.expansion_probability}})
    for i, r in enumerate(out[:limit], 1):
        r["rank"] = i
    return out[:limit]


def versions(db: Session, event_id: int) -> list[int]:
    return [v for (v,) in db.execute(select(PriorityResult.version).where(PriorityResult.event_id == event_id).distinct().order_by(PriorityResult.version))]


def snapshot_at(db: Session, event_id: int, version: int) -> dict[str, dict]:
    return {r.h3_index: {**r.snapshot, "level": r.level, "score": r.score} for r in db.scalars(select(PriorityResult).where(PriorityResult.event_id == event_id, PriorityResult.version == version))}


def what_changed(db: Session, event: Event, frm: int | None = None, to: int | None = None) -> dict:
    vs = versions(db, event.id)
    if len(vs) < 2:
        return {"available": False, "message": "Only one assessment exists. Run a new analysis or submit field reports to enable comparison.", "versions": vs}
    to = to or vs[-1]
    if frm is None:
        frm = vs[vs.index(to) - 1] if to in vs and vs.index(to) > 0 else vs[0]
    prev, cur = snapshot_at(db, event.id, frm), snapshot_at(db, event.id, to)
    rh = event.config.get("road_hist", {})
    cell_no = {c.h3_index: c.cell_no for c in cells_of(db, event.id)}
    res = escalation.what_changed(prev, cur, int(rh.get(str(frm), 0)), int(rh.get(str(to), 0)))
    res["escalations"] = escalation.diff_priorities(prev, cur, cell_no)
    res.update({"available": True, "from_version": frm, "to_version": to, "versions": vs})
    return res
