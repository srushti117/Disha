"""Cross-cutting helpers: audit log, incident timeline, alert persistence + notification dispatch."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..engines.alerts import DEFAULT_RECIPIENTS, get_provider
from ..models import Alert, AuditLog, Event, IncidentTimeline, Notification

log = logging.getLogger("disha")
settings = get_settings()


def now() -> datetime:
    return datetime.now(timezone.utc)


def audit(db: Session, user, action: str, target: str = "", event_id: int | None = None, reason: str = "", detail: dict | None = None):
    db.add(AuditLog(user_id=getattr(user, "id", None), user_email=getattr(user, "email", "system"), event_id=event_id,
                    action=action, target=target, reason=reason, detail=detail or {}))


def timeline(db: Session, event_id: int, kind: str, title: str, detail: str = "", h3_index: str | None = None, at: datetime | None = None):
    db.add(IncidentTimeline(event_id=event_id, kind=kind, title=title, detail=detail, h3_index=h3_index, at=at or now()))


def persist_alerts(db: Session, event: Event, specs: list[dict]) -> list[Alert]:
    out = []
    for s in specs:
        a = Alert(event_id=event.id, trigger=s["trigger"], severity=s["severity"], title=s["title"], detail=s["detail"],
                  h3_index=s.get("h3_index"), data=s.get("data", {}))
        db.add(a)
        db.flush()
        for ch in s.get("channels", ["dashboard"]):
            prov = get_provider(ch, settings.notify_provider)
            status = prov.send(DEFAULT_RECIPIENTS.get(ch, ""), a.title, a.detail)
            db.add(Notification(event_id=event.id, alert_id=a.id, channel=ch, recipient=DEFAULT_RECIPIENTS.get(ch, ""),
                                body=f"{a.title}\n{a.detail}", provider=prov.name, status=status))
        out.append(a)
    return out
