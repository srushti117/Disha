"""Field responder workflow: missions, reports, photo analysis, feedback loop (closes DETECT -> VERIFY -> RECALCULATE)."""
from __future__ import annotations

import io
import random
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..engines.field_cv import analyse_photo
from ..models import Event, FieldPhoto, FieldReport, H3Cell, Mission, ResourceAssignment
from .common import audit, now, timeline
from .twin import recompute

settings = get_settings()
VERDICTS = ("confirmed", "false_alarm", "partially_affected", "severe", "resolved")


def ensure_missions(db: Session, event: Event) -> list[Mission]:
    existing = {m.h3_index: m for m in db.scalars(select(Mission).where(Mission.event_id == event.id))}
    n = len(existing)
    p1 = db.scalars(select(H3Cell).where(H3Cell.event_id == event.id, H3Cell.priority_level.in_(["P1", "P2"])).order_by(H3Cell.priority_score.desc()).limit(24)).all()
    for c in p1:
        if c.h3_index not in existing and c.field_status != "resolved":
            n += 1
            kind = "SEARCH & RESCUE" if c.priority_level == "P1" else "RELIEF & EVACUATION"
            m = Mission(event_id=event.id, number=n, h3_index=c.h3_index, kind=kind, brief="; ".join(r["label"] for r in c.reason_codes[:3]))
            db.add(m)
            existing[c.h3_index] = m
    db.flush()
    return sorted(existing.values(), key=lambda m: m.number)


def mission_view(db: Session, m: Mission) -> dict:
    c = db.scalars(select(H3Cell).where(H3Cell.event_id == m.event_id, H3Cell.h3_index == m.h3_index)).first()
    return {"id": m.id, "number": m.number, "label": f"MISSION #{m.number:03d}", "h3_index": m.h3_index, "cell_no": c.cell_no if c else None, "status": m.status,
            "kind": m.kind, "priority": c.priority_level if c else None, "population": c.population_exposed if c else None,
            "risk": "HIGH" if c and c.priority_score >= 0.48 else "MODERATE" if c and c.priority_score >= 0.34 else "LOW", "brief": m.brief,
            "lat": c.lat if c else None, "lon": c.lon if c else None, "field_status": c.field_status if c else None, "assigned_to": m.assigned_to,
            "recommended_action": c.recommended_action if c else ""}


def _save_photo(event_id: int, data: bytes) -> str:
    d = settings.data_dir / "events" / str(event_id) / "photos"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{uuid.uuid4().hex}.jpg"
    Image.open(io.BytesIO(data)).convert("RGB").save(p, "JPEG", quality=85)
    return str(p.relative_to(settings.data_dir))


def submit_report(db: Session, event: Event, user, h3_index: str, verdict: str, notes: str = "", observed_severity: float | None = None,
                  photos: list[bytes] | None = None, lat: float | None = None, lon: float | None = None, simulated: bool = False,
                  mission_id: int | None = None) -> dict:
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}")
    cell = db.scalars(select(H3Cell).where(H3Cell.event_id == event.id, H3Cell.h3_index == h3_index)).first()
    if cell is None:
        raise KeyError(h3_index)
    before = {"level": cell.priority_level, "score": cell.priority_score, "severity": cell.severity, "confidence": cell.confidence}
    analyses = []
    rep = FieldReport(event_id=event.id, h3_index=h3_index, mission_id=mission_id, user_id=getattr(user, "id", None), verdict=verdict, notes=notes,
                      observed_severity=observed_severity, lat=lat, lon=lon, is_simulated=simulated)
    db.add(rep)
    db.flush()
    for data in photos or []:
        an = analyse_photo(data)
        analyses.append(an)
        db.add(FieldPhoto(report_id=rep.id, event_id=event.id, path=_save_photo(event.id, data), analysis=an))
    if analyses and observed_severity is None and verdict == "severe":
        sev = {"High": 0.9, "Moderate": 0.7, "Low": 0.5}.get(analyses[0]["estimated_severity"])
        rep.observed_severity = sev
    cn = cell.cell_no
    timeline(db, event.id, "field", f"Field report received - Cell {cn:02d}: {verdict.replace('_', ' ')}", notes[:200], h3_index, )
    if mission_id:
        m = db.get(Mission, mission_id)
        if m and verdict == "resolved":
            m.status = "resolved"
    audit(db, user, "field.report", f"Cell {cn:02d}", event.id, reason=notes[:200], detail={"verdict": verdict, "simulated": simulated})
    out = recompute(db, event, trigger="field_report", user=user)
    db.refresh(cell)
    after = {"level": cell.priority_level, "score": cell.priority_score, "severity": cell.severity, "confidence": cell.confidence}
    rep.effect = {"before": before, "after": after, "note": cell.components.get("field_note", "")}
    timeline(db, event.id, "priority", f"Priority recalculated - Cell {cn:02d}: {before['level']} -> {after['level']}", cell.components.get("field_note", ""), h3_index)
    if verdict == "resolved":
        for a in db.scalars(select(ResourceAssignment).where(ResourceAssignment.event_id == event.id, ResourceAssignment.h3_index == h3_index, ResourceAssignment.status == "dispatched")):
            a.status = "completed"
    return {"report_id": rep.id, "cell_no": cn, "before": before, "after": after, "effect_note": rep.effect["note"], "photo_analysis": analyses,
            "escalations": out["escalations"], "assessment_version": event.assessment_version, "field_verified": True}


def synth_photo(kind: str = "flood", seed: int = 0) -> bytes:
    """A clearly synthetic placeholder 'field photo' for demo mode (drawn, not photographic)."""
    rnd = random.Random(seed)
    W, H = 480, 320
    img = Image.new("RGB", (W, H), (150, 170, 190))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, int(H * 0.38)], fill=(165, 185, 205))
    for i in range(6):
        x = rnd.randint(0, W - 80)
        d.rectangle([x, int(H * 0.12), x + rnd.randint(50, 90), int(H * 0.4)], fill=(120 + rnd.randint(0, 40), 110, 100))
    if kind == "fire":
        d.rectangle([0, int(H * 0.38), W, H], fill=(60, 50, 40))
        for i in range(30):
            x, y = rnd.randint(0, W), rnd.randint(int(H * 0.4), H)
            d.ellipse([x - 25, y - 25, x + 25, y + 25], fill=(255, 120 + rnd.randint(0, 80), 10))
    else:
        d.rectangle([0, int(H * 0.38), W, H], fill=(110, 140, 170) if kind != "mud" else (140, 110, 80))
        d.polygon([(int(W * 0.35), int(H * 0.38)), (int(W * 0.65), int(H * 0.38)), (W, H), (0, H)], fill=(125, 128, 130))
        d.rectangle([0, int(H * 0.55), W, H], fill=(120, 105, 85) if kind == "mud" else (95, 130, 165))
        for i in range(10):
            x, y = rnd.randint(0, W), rnd.randint(int(H * 0.6), H)
            d.ellipse([x - 20, y - 6, x + 20, y + 6], fill=(105, 75, 50))
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()
