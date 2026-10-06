"""Seed demo accounts, model registry and (optionally) demo events. Demo credentials are clearly marked."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from .core.config import get_settings
from .core.db import SessionLocal, init_db
from .core.security import ROLES, hash_password
from .models import ModelVersion, Role, User

log = logging.getLogger("disha.seed")
settings = get_settings()

DEMO_USERS = [
    ("admin@disha.demo", "Demo Admin", "admin"), ("commander@disha.demo", "Demo Commander", "commander"),
    ("analyst@disha.demo", "Demo Analyst", "analyst"), ("responder@disha.demo", "Demo Field Responder", "responder"),
    ("observer@disha.demo", "Demo Observer", "observer"),
]
ROLE_DESC = {"admin": "Full access", "commander": "Events, priority, resources, routes, reports", "analyst": "Satellite, AI, change detection, data",
             "responder": "Missions, navigation, photos, status", "observer": "Read-only dashboard"}

MODELS = [
    dict(name="disha-rule-based", version="1.0.0", hazard="flood", kind="rule", status="active", training_dataset="n/a (threshold/rule based)",
         notes="SAR log-ratio + Otsu + terrain/permanent-water masks + NDWI confirmation. No learned weights; accuracy not established on real events."),
    dict(name="disha-rule-based", version="1.0.0", hazard="wildfire", kind="rule", status="active", training_dataset="n/a", notes="dNBR + VIIRS hotspots + SAR support."),
    dict(name="disha-rule-based", version="1.0.0", hazard="landslide", kind="rule", status="active", training_dataset="n/a", notes="dNDVI + slope + SAR change logistic."),
    dict(name="disha-rule-based", version="1.0.0", hazard="cyclone", kind="rule", status="active", training_dataset="n/a", notes="SAR change + dNDVI + roof proxy + surge rule."),
    dict(name="disha-random-forest", version="0.1.0", hazard="flood", kind="ml", status="not_trained", training_dataset="Sen1Floods11 (planned)", notes="Trainable via RandomForestDetector.fit(); no weights bundled."),
    dict(name="siamese-unet", version="adapter-0.1", hazard="flood", kind="dl", status="adapter_only", training_dataset="xBD + Sen1Floods11 (planned)", notes="ONNX adapter. Weights not bundled."),
    dict(name="changeformer", version="adapter-0.1", hazard="flood", kind="dl", status="adapter_only", training_dataset="LEVIR-CD (planned)", notes="ONNX adapter. Weights not bundled."),
    dict(name="disha-risk-propagation", version="0.1", hazard="flood", kind="rule", status="active", training_dataset="n/a (hand-set coefficients)", notes="Heuristic expansion model; not validated."),
    dict(name="disha-photo-heuristics", version="0.1", hazard="all", kind="rule", status="active", training_dataset="n/a", notes="Colour/texture heuristics; not a trained CV model."),
]


def seed_core(db) -> None:
    for r in ROLES:
        if not db.scalars(select(Role).where(Role.name == r)).first():
            db.add(Role(name=r, description=ROLE_DESC[r]))
    if settings.seed_demo_accounts:
        for email, name, role in DEMO_USERS:
            if not db.scalars(select(User).where(User.email == email)).first():
                db.add(User(email=email, name=name, role=role, hashed_password=hash_password(settings.demo_password), is_demo=True))
    for m in MODELS:
        if not db.scalars(select(ModelVersion).where(ModelVersion.name == m["name"], ModelVersion.hazard == m["hazard"], ModelVersion.version == m["version"])).first():
            db.add(ModelVersion(**m))
    db.commit()
    for m in MODELS:  # models/ directory carries metadata too
        p = settings.models_dir / f"{m['name']}_{m['hazard']}.json"
        if not p.exists():
            p.write_text(json.dumps({**m, "accuracy": None, "written": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf8")


def main():
    init_db()
    with SessionLocal() as db:
        seed_core(db)
    print("Seeded roles, demo accounts and model registry.")


if __name__ == "__main__":
    main()
