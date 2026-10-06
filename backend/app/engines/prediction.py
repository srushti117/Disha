"""Risk expansion prediction (+6/12/24/48 h): transparent heuristic risk-propagation model.

MODEL: disha-risk-propagation v0.1 - a logistic model with hand-set coefficients over neighbour hazard
state, terrain, forecast rainfall and river trend. It is NOT trained or validated against observed event
progression; every output is an estimate with a probability and a confidence label that decays with horizon.
"""
from __future__ import annotations

import math

import h3
import numpy as np

from .priority import PriorityInput, compute_priority, confidence_label

MODEL_NAME, MODEL_VERSION = "disha-risk-propagation", "0.1"
HORIZONS = (6, 12, 24, 48)

COEF = {
    "flood": dict(b=-2.4, ring1=3.0, ring2=1.4, low=1.6, rain=1.8, river=0.9, persist=1.6, slope=0.0, wind=0.0),
    "wildfire": dict(b=-2.6, ring1=3.2, ring2=1.2, low=0.0, rain=-2.0, river=0.0, persist=1.2, slope=1.0, wind=0.6),
    "landslide": dict(b=-2.8, ring1=2.2, ring2=0.8, low=0.0, rain=2.2, river=0.0, persist=1.5, slope=2.4, wind=0.0),
    "cyclone": dict(b=-3.0, ring1=1.5, ring2=0.6, low=1.2, rain=1.0, river=0.0, persist=1.0, slope=0.0, wind=0.0),
}


def _sig(z):
    return 1 / (1 + math.exp(-z))


def _rain_norm(weather: dict, h: int) -> float:
    return min(1.0, _rain_mm(weather, h) / 120.0)


def _rain_mm(weather: dict, h: int) -> float:
    r = weather.get("rainfall_mm", {})
    if not r:
        return 0.0
    key = min((int(k) for k in r), key=lambda k: abs(k - min(h, max(int(x) for x in r))))
    return float(r[str(key)])


def predict(cells: list[dict], weather: dict, hazard: str, weights: dict, thresholds: dict, exposure_ref: float,
            horizons=HORIZONS) -> list[dict]:
    """cells: dicts with h3_index, severity, hazard_fraction, elevation_m, slope_deg, confidence, population, road_m,
    infra_presence, vulnerability_score, access_loss, + fields for PriorityInput. Returns one record per (cell, horizon)."""
    coef = COEF.get(hazard, COEF["flood"])
    by_id = {c["h3_index"]: c for c in cells}
    affected_elev = [c["elevation_m"] for c in cells if c["severity"] >= 0.1]
    surface = float(np.percentile(affected_elev, 90)) if len(affected_elev) > 5 else None
    trend = float(weather.get("river_level_trend_m_per_h", 0.0))
    wind = min(1.0, float(weather.get("wind_kmh", 0)) / 60.0)
    out = []
    for c in cells:
        r1 = [by_id[n]["hazard_fraction"] for n in h3.grid_ring(c["h3_index"], 1) if n in by_id]
        r2 = [by_id[n]["hazard_fraction"] for n in h3.grid_ring(c["h3_index"], 2) if n in by_id]
        ring1 = float(np.mean(r1)) if r1 else 0.0
        ring2 = float(np.mean(r2)) if r2 else 0.0
        low = 0.0 if surface is None else float(np.clip((surface - c["elevation_m"]) / 4.0, 0, 1))
        slope_n = float(np.clip(c.get("slope_deg", 0) / 35.0, 0, 1))
        for h in horizons:
            rain = _rain_norm(weather, h)
            river = float(np.clip(trend * h / 1.5, 0, 1))
            terms = {
                "Neighbouring cells already affected": coef["ring1"] * ring1 + coef["ring2"] * ring2,
                "Low-lying terrain relative to the affected surface": coef["low"] * low,
                f"Forecast rainfall ({_rain_mm(weather, h):.0f} mm in window)": coef["rain"] * rain,
                "Rising river level": coef["river"] * river,
                "Already affected (persistence)": coef["persist"] * c["hazard_fraction"],
                "Steep terrain": coef["slope"] * slope_n,
                "Wind-driven spread": coef["wind"] * wind * ring1,
            }
            z = coef["b"] + sum(terms.values())
            p = float(np.clip(_sig(z), 0.02, 0.97))
            growth = 0.25 + 0.4 * rain if hazard == "flood" else 0.3
            sev0 = c["severity"]
            if sev0 < 0.03 and p < 0.25:
                sev_pred = 0.0
            else:
                sev_pred = float(np.clip(sev0 + (p * 0.6 + 0.1) * (1 - sev0) * growth * (1 + 0.3 * math.log2(h / 6 + 1)) if sev0 >= 0.03 else p * 0.55 * growth * 1.6, 0, 1))
            hf0 = c["hazard_fraction"]
            hf_pred = float(np.clip(hf0 + (1 - hf0) * p * growth * 1.2, 0, 1)) if sev_pred > 0 else 0.0
            exp_pred = int(round(c["population"] * hf_pred))
            conf_base = c["confidence"] if sev0 >= 0.03 else 0.7
            conf = round(conf_base * (1 - 0.012 * h), 3)
            access_pred = max(c["access_loss"], min(0.9, 1.2 * sev_pred)) if c.get("road_m", 0) > 0 else c["access_loss"]
            infra_pred = c.get("infra_presence", 0.0) * (0.2 + 0.8 * min(1.0, max(hf_pred, 0.6 * ring1))) if sev_pred > 0.03 else 0.0
            pi = PriorityInput(
                severity=sev_pred, confidence=conf, exposure_pop_norm=min(1.0, exp_pred / max(exposure_ref, 1)),
                vulnerability=c.get("vulnerability_score", 0.0), infrastructure_score=max(infra_pred, c.get("infrastructure_score", 0.0) if sev0 >= 0.03 else infra_pred),
                access_loss=access_pred, population_exposed=exp_pred, hazard=hazard,
            )
            res = compute_priority(pi, weights, thresholds)
            drivers = [k for k, v in sorted(terms.items(), key=lambda kv: -kv[1]) if v > 0.15][:3]
            out.append({
                "h3_index": c["h3_index"], "horizon_h": h, "expansion_probability": round(p, 3), "predicted_severity": round(sev_pred, 3),
                "predicted_score": res.score, "predicted_level": res.level, "current_level": c["priority_level"],
                "confidence": conf, "confidence_label": confidence_label(conf), "drivers": drivers,
                "predicted_population_exposed": exp_pred,
            })
    return out
