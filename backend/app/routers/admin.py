from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import get_db
from ..core.security import PERMISSIONS, current_user, require
from ..models import AuditLog, DataSource, ModelVersion, User
from .auth import user_out

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    s = get_settings()
    db.execute(select(1))
    return {"status": "ok", "environment": s.environment, "database": s.database_url.split(":")[0], "demo_mode": s.demo_mode, "notify_provider": s.notify_provider}


@router.get("/admin/users")
def users(db: Session = Depends(get_db), _=Depends(require("admin"))):
    return [user_out(u) for u in db.scalars(select(User).order_by(User.id))]


@router.get("/admin/audit")
def audit(event_id: int | None = None, limit: int = Query(200, le=1000), db: Session = Depends(get_db), _=Depends(require("event.write"))):
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if event_id:
        q = q.where(AuditLog.event_id == event_id)
    return [{"id": a.id, "at": a.at.isoformat(), "who": a.user_email, "what": a.action, "where": a.target, "reason": a.reason, "event_id": a.event_id, "detail": a.detail}
            for a in db.scalars(q)]


@router.get("/models")
def models(db: Session = Depends(get_db), _=Depends(current_user)):
    return [{"id": m.id, "name": m.name, "version": m.version, "hazard": m.hazard, "kind": m.kind, "status": m.status, "training_dataset": m.training_dataset,
             "accuracy": m.accuracy, "trained_on": m.trained_on.isoformat() if m.trained_on else None, "notes": m.notes} for m in db.scalars(select(ModelVersion).order_by(ModelVersion.id))]


@router.get("/admin/data-sources")
def sources(db: Session = Depends(get_db), _=Depends(require("data.manage"))):
    return [{"event_id": d.event_id, "key": d.key, "name": d.name, "provider": d.provider, "simulated": d.is_simulated, "quality": d.quality, "last_updated": d.last_updated.isoformat()}
            for d in db.scalars(select(DataSource).order_by(DataSource.event_id.desc(), DataSource.key))]


@router.get("/permissions")
def permissions(_=Depends(current_user)):
    return PERMISSIONS
