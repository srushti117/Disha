from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import Event


def get_event(event_id: int, db: Session = Depends(get_db)) -> Event:
    ev = db.get(Event, event_id)
    if not ev:
        raise HTTPException(404, f"Event {event_id} not found")
    return ev


def need_analysis(ev: Event = Depends(get_event)) -> Event:
    if not ev.assessment_version:
        raise HTTPException(409, "Event has not been analysed yet. POST /api/events/{id}/process first.")
    return ev
