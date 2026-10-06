"""Routes, shelters, resources."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import current_user, require
from ..engines.resources import KIND_LABEL, KIND_ORDER
from ..models import Event, H3Cell, Mission, Resource, ResourceAssignment, Route
from ..services import response, summary
from ..services.common import audit, timeline
from ..services.field import ensure_missions
from ..services.twin import recompute
from .deps import get_event, need_analysis

router = APIRouter(prefix="/api/events/{event_id}", tags=["response"])


class RouteIn(BaseModel):
    cell_no: int | None = None
    h3_index: str | None = None
    origin_lat: float | None = Field(default=None, ge=-90, le=90)
    origin_lon: float | None = Field(default=None, ge=-180, le=180)


@router.post("/routes")
def plan_route(body: RouteIn, e: Event = Depends(need_analysis), db: Session = Depends(get_db), user=Depends(require("route.plan"))):
    h3i = body.h3_index
    if not h3i:
        c = db.scalars(select(H3Cell).where(H3Cell.event_id == e.id, H3Cell.cell_no == body.cell_no)).first()
        if not c:
            raise HTTPException(404, "Cell not found")
        h3i = c.h3_index
    origin = (body.origin_lat, body.origin_lon) if body.origin_lat is not None and body.origin_lon is not None else None
    try:
        out = response.compute_routes(db, e, h3i, origin)
    except KeyError:
        raise HTTPException(404, "Cell not found")
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    audit(db, user, "route.plan", f"Cell {out['target']['cell_no']:02d}", e.id, detail={"recommended": out["recommended"]})
    db.commit()
    return out


@router.get("/routes")
def list_routes(e: Event = Depends(get_event), db: Session = Depends(get_db), _=Depends(current_user)):
    cells = {c.h3_index: c for c in db.scalars(select(H3Cell).where(H3Cell.event_id == e.id))}
    rows = db.scalars(select(Route).where(Route.event_id == e.id).order_by(Route.target_h3, Route.kind)).all()
    grouped: dict[str, list] = {}
    for r in rows:
        grouped.setdefault(r.target_h3, []).append({"kind": r.kind, "distance_km": r.distance_km, "eta_min": r.eta_min, "risk": r.risk, "blocked_segments": r.blocked_segments,
                                                    "feasible": r.feasible, "recommended": r.recommended, "geometry": r.geom, "notes": r.notes})
    return {"targets": [{"h3_index": h, "cell_no": cells[h].cell_no, "priority_level": cells[h].priority_level, "routes": v} for h, v in grouped.items() if h in cells],
            "bases": e.config.get("bases", [])}


@router.get("/shelters")
def shelters(e: Event = Depends(need_analysis), db: Session = Depends(get_db), _=Depends(current_user)):
    return response.evacuation_plan(db, e)


@router.get("/resources")
def resources(e: Event = Depends(get_event), db: Session = Depends(get_db), _=Depends(current_user)):
    s = response.resource_summary(db, e.id)
    s["kinds"] = [{"kind": k, "label": KIND_LABEL[k]} for k in KIND_ORDER]
    s["assignments"] = [{"id": a.id, "resource": a.resource.name, "kind": a.resource.kind, "h3_index": a.h3_index, "status": a.status, "reason": a.reason, "eta_min": a.eta_min}
                        for a in db.scalars(select(ResourceAssignment).where(ResourceAssignment.event_id == e.id, ResourceAssignment.status.in_(["recommended", "dispatched"])).order_by(ResourceAssignment.id))]
    cells = {c.h3_index: c.cell_no for c in db.scalars(select(H3Cell).where(H3Cell.event_id == e.id))}
    for a in s["assignments"]:
        a["cell_no"] = cells.get(a["h3_index"])
    return s


class CountsIn(BaseModel):
    counts: dict[str, int]


def _validate_counts(counts: dict[str, int]):
    for k, v in counts.items():
        if k not in KIND_ORDER:
            raise HTTPException(422, f"Unknown resource kind '{k}'")
        if not 0 <= v <= 200:
            raise HTTPException(422, "counts must be between 0 and 200")


@router.put("/resources/roster")
def set_roster(body: CountsIn, e: Event = Depends(need_analysis), db: Session = Depends(get_db), user=Depends(require("resource.assign"))):
    """Set the number of AVAILABLE units per kind (adds units at the response bases or marks surplus unavailable)."""
    _validate_counts(body.counts)
    bases = e.config.get("bases", [])
    for kind, want in body.counts.items():
        units = db.scalars(select(Resource).where(Resource.event_id == e.id, Resource.kind == kind).order_by(Resource.id)).all()
        avail = [u for u in units if u.status == "available"]
        if want > len(avail):
            for i in range(want - len(avail)):
                b = bases[(len(units) + i) % max(len(bases), 1)] if bases else {"lat": 0, "lon": 0}
                db.add(Resource(event_id=e.id, kind=kind, name=f"{KIND_LABEL[kind]} {len(units) + i + 1:02d}", status="available", lat=b["lat"], lon=b["lon"],
                                speed_kmh=units[0].speed_kmh if units else 35))
        else:
            for u in avail[want:]:
                u.status = "unavailable"
    audit(db, user, "resource.roster", e.code, e.id, detail=body.counts)
    db.commit()
    return response.resource_summary(db, e.id)


class OptimiseIn(BaseModel):
    commit: bool = True


@router.post("/resources/optimise")
def optimise(body: OptimiseIn, e: Event = Depends(need_analysis), db: Session = Depends(get_db), user=Depends(require("resource.assign"))):
    out = response.allocation(db, e, commit=body.commit, user=user)
    e.config = {**e.config, "coverage": out["metrics"]}
    if body.commit:
        timeline(db, e.id, "resource", "Resource allocation optimised", f"{out['metrics']['units_assigned']} units recommended; P1 coverage {out['metrics']['p1_coverage_pct']}%.")
        audit(db, user, "resource.optimise", e.code, e.id, reason="Priority-based allocation", detail=out["metrics"])
    db.commit()
    return out


@router.post("/resources/simulate")
def simulate(body: CountsIn, e: Event = Depends(need_analysis), db: Session = Depends(get_db), _=Depends(require("resource.assign"))):
    _validate_counts(body.counts)
    out = response.allocation(db, e, counts=body.counts)
    return {"metrics": out["metrics"], "assignments": out["assignments"], "unmet": out["unmet"], "counts": body.counts, "simulated": True,
            "note": "What-if only: nothing was assigned or dispatched."}


class DispatchIn(BaseModel):
    assignment_ids: list[int] | None = None
    reason: str = "P1 priority"


@router.post("/resources/dispatch")
def dispatch(body: DispatchIn, e: Event = Depends(need_analysis), db: Session = Depends(get_db), user=Depends(require("resource.assign"))):
    q = select(ResourceAssignment).where(ResourceAssignment.event_id == e.id, ResourceAssignment.status == "recommended")
    if body.assignment_ids:
        q = q.where(ResourceAssignment.id.in_(body.assignment_ids))
    rows = db.scalars(q).all()
    if not rows:
        raise HTTPException(409, "No recommended assignments to dispatch. Run OPTIMISE RESOURCES first.")
    cells = {c.h3_index: c for c in db.scalars(select(H3Cell).where(H3Cell.event_id == e.id))}
    ensure_missions(db, e)
    for a in rows:
        a.status = "dispatched"
        a.resource.status, a.resource.assigned_cell = "deployed", a.h3_index
        a.assigned_by = user.id
        audit(db, user, "resource.assign", f"{a.resource.name} -> Cell {cells[a.h3_index].cell_no:02d}", e.id, reason=body.reason or a.reason, detail={"eta_min": a.eta_min})
    timeline(db, e.id, "dispatch", f"{len(rows)} resource(s) dispatched", "; ".join(f"{a.resource.name}->Cell {cells[a.h3_index].cell_no:02d}" for a in rows[:6]))
    db.commit()
    return {"dispatched": len(rows), "summary": response.resource_summary(db, e.id)}


@router.post("/resources/release")
def release(e: Event = Depends(get_event), db: Session = Depends(get_db), user=Depends(require("resource.assign"))):
    n = 0
    for a in db.scalars(select(ResourceAssignment).where(ResourceAssignment.event_id == e.id, ResourceAssignment.status.in_(["recommended", "dispatched"]))):
        a.status = "cancelled"
        a.resource.status, a.resource.assigned_cell = "available", None
        n += 1
    audit(db, user, "resource.release", e.code, e.id)
    db.commit()
    return {"released": n}
