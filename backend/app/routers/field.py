"""Field responder API: missions, reports, photos, simulation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import get_db
from ..core.security import current_user, require
from ..models import Event, FieldPhoto, FieldReport, H3Cell, Mission
from ..services import field as field_svc
from ..services.common import audit
from .deps import get_event, need_analysis

router = APIRouter(prefix="/api/events/{event_id}", tags=["field"])
settings = get_settings()
MAX_PHOTO = 8 * 1024 * 1024


@router.get("/missions")
def missions(e: Event = Depends(need_analysis), db: Session = Depends(get_db), user=Depends(current_user)):
    ms = field_svc.ensure_missions(db, e)
    db.commit()
    out = [field_svc.mission_view(db, m) for m in ms]
    if user.role == "responder":
        out = [m for m in out if m["assigned_to"] in (None, user.id)]
    return out


class MissionStatus(BaseModel):
    status: str


@router.post("/missions/{mission_id}/status")
def mission_status(mission_id: int, body: MissionStatus, e: Event = Depends(get_event), db: Session = Depends(get_db), user=Depends(require("field.report"))):
    if body.status not in ("accepted", "en_route", "on_site", "resolved", "pending"):
        raise HTTPException(422, "invalid status")
    m = db.get(Mission, mission_id)
    if not m or m.event_id != e.id:
        raise HTTPException(404, "Mission not found")
    m.status = body.status
    if body.status == "accepted":
        m.assigned_to = user.id
    audit(db, user, "mission.status", f"Mission #{m.number:03d}", e.id, detail={"status": body.status})
    db.commit()
    return field_svc.mission_view(db, m)


async def _read_photos(files: list[UploadFile] | None) -> list[bytes]:
    out = []
    for f in files or []:
        if f.content_type not in ("image/jpeg", "image/png", "image/webp"):
            raise HTTPException(415, "Only JPEG/PNG/WebP photos are accepted")
        data = await f.read()
        if len(data) > MAX_PHOTO:
            raise HTTPException(413, "Photo exceeds 8 MB")
        out.append(data)
    return out


@router.post("/field-reports", status_code=201)
async def submit(h3_index: str = Form(...), verdict: str = Form(...), notes: str = Form(""), observed_severity: float | None = Form(None),
                 mission_id: int | None = Form(None), lat: float | None = Form(None), lon: float | None = Form(None),
                 photos: list[UploadFile] | None = File(None), e: Event = Depends(need_analysis), db: Session = Depends(get_db), user=Depends(require("field.report"))):
    data = await _read_photos(photos)
    try:
        out = field_svc.submit_report(db, e, user, h3_index, verdict, notes[:2000], observed_severity, data, lat, lon, False, mission_id)
    except KeyError:
        raise HTTPException(404, "Cell not found")
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    db.commit()
    return out


class SimIn(BaseModel):
    h3_index: str | None = None
    cell_no: int | None = None
    verdict: str = "severe"
    kind: str = "flood"
    notes: str = "SIMULATED field report for demonstration."


@router.post("/field-reports/simulate", status_code=201)
def simulate(body: SimIn, e: Event = Depends(need_analysis), db: Session = Depends(get_db), user=Depends(require("field.report"))):
    h3i = body.h3_index
    if not h3i:
        c = db.scalars(select(H3Cell).where(H3Cell.event_id == e.id, H3Cell.cell_no == body.cell_no)).first()
        if not c:
            raise HTTPException(404, "Cell not found")
        h3i = c.h3_index
    try:
        out = field_svc.submit_report(db, e, user, h3i, body.verdict, body.notes, None, [field_svc.synth_photo(body.kind, seed=e.id + (body.cell_no or 0))], None, None, True)
    except KeyError:
        raise HTTPException(404, "Cell not found")
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    db.commit()
    return {**out, "label": "SIMULATED field report and synthetic placeholder image (demonstration only)"}


@router.get("/field-reports")
def list_reports(e: Event = Depends(get_event), db: Session = Depends(get_db), _=Depends(current_user)):
    cells = {c.h3_index: c.cell_no for c in db.scalars(select(H3Cell).where(H3Cell.event_id == e.id))}
    rows = db.scalars(select(FieldReport).where(FieldReport.event_id == e.id).order_by(FieldReport.created_at.desc())).all()
    out = []
    for r in rows:
        photos = db.scalars(select(FieldPhoto).where(FieldPhoto.report_id == r.id)).all()
        out.append({"id": r.id, "h3_index": r.h3_index, "cell_no": cells.get(r.h3_index), "verdict": r.verdict, "notes": r.notes, "at": r.created_at.isoformat(), "simulated": r.is_simulated,
                    "effect": r.effect, "photos": [{"id": p.id, "analysis": p.analysis} for p in photos]})
    return out


@router.get("/field-reports/training-export")
def training_export(e: Event = Depends(get_event), db: Session = Depends(get_db), _=Depends(require("data.manage"))):
    """Field-verified labels for future active learning / model retraining."""
    cells = {c.h3_index: c for c in db.scalars(select(H3Cell).where(H3Cell.event_id == e.id))}
    return {"event": e.code, "labels": [{"h3_index": r.h3_index, "lat": cells[r.h3_index].lat, "lon": cells[r.h3_index].lon, "verdict": r.verdict, "simulated": r.is_simulated,
                                         "model_severity": (cells[r.h3_index].components.get("base") or {}).get("severity"), "observed_severity": r.observed_severity}
                                        for r in db.scalars(select(FieldReport).where(FieldReport.event_id == e.id)) if r.h3_index in cells]}


@router.get("/field-photos/{photo_id}")
def photo(photo_id: int, e: Event = Depends(get_event), db: Session = Depends(get_db), _=Depends(current_user)):
    p = db.get(FieldPhoto, photo_id)
    if not p or p.event_id != e.id:
        raise HTTPException(404)
    path = (settings.data_dir / p.path).resolve()
    if settings.data_dir.resolve() not in path.parents or not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg")
