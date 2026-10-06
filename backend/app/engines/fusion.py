"""Multi-source fusion: per-location provenance + overall confidence + freshness (spec §10, §37, §50)."""
from __future__ import annotations

from datetime import datetime, timezone

from .priority import confidence_label

SOURCE_WEIGHTS = {"satellite": 0.45, "population": 0.15, "roads": 0.15, "weather": 0.07, "infrastructure": 0.08, "field": 0.10}
LABELS = {"satellite": "Satellite", "weather": "Weather", "population": "Population", "roads": "Road Network",
          "infrastructure": "Infrastructure", "field": "Field Report"}


def _hours_since(ts: datetime | None, now: datetime | None = None) -> float | None:
    if ts is None:
        return None
    now = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0.0, (now - ts).total_seconds() / 3600)


def freshness_factor(age_h: float | None, stale_after_h: float) -> float:
    if age_h is None:
        return 0.5
    if age_h <= stale_after_h:
        return 1.0
    return max(0.3, 1.0 - 0.15 * (age_h - stale_after_h) / max(stale_after_h, 1))


def source_status(key: str, available: bool, quality: float, timestamp: datetime | None, stale_after_h: float,
                  simulated: bool, now: datetime | None = None) -> dict:
    age = _hours_since(timestamp, now)
    return {
        "key": key, "label": LABELS.get(key, key), "available": bool(available), "quality": round(float(quality), 3),
        "timestamp": timestamp.isoformat() if timestamp else None, "age_hours": None if age is None else round(age, 1),
        "stale": bool(age is not None and age > stale_after_h), "simulated": simulated,
    }


def overall_confidence(sources: list[dict], stale_after: dict[str, float] | None = None) -> tuple[float, str]:
    """Weighted mean of quality x freshness over available sources; missing key sources lower the ceiling."""
    num = den = 0.0
    for s in sources:
        w = SOURCE_WEIGHTS.get(s["key"], 0.05)
        if not s["available"]:
            continue
        ff = 0.6 if s.get("stale") else 1.0
        num += w * s["quality"] * ff
        den += w
    if den == 0:
        return 0.0, confidence_label(None)
    coverage = den / sum(w for k, w in SOURCE_WEIGHTS.items() if k != "field")  # field reports are a bonus, not required
    coverage = min(1.0, coverage)
    score = (num / den) * (0.75 + 0.25 * coverage)
    return round(min(score, 0.99), 3), confidence_label(score)
