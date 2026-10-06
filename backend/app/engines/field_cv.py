"""Field photo analysis (HEURISTIC computer-vision prototype).

Uses colour/texture statistics only - there is no trained model behind this. It reports what the pixels
suggest, caps confidence, and never claims measured depths/areas. Replace `analyse_photo` with an ONNX/
vision-model call for production.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageFilter

MODEL_NAME, MODEL_VERSION = "disha-photo-heuristics", "0.1 (colour/texture heuristics, untrained)"


def analyse_photo(data: bytes) -> dict:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((320, 320))
    rgb = np.asarray(img).astype(np.float32) / 255.0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    val = mx
    h = img.convert("HSV")
    hue = np.asarray(h)[..., 0].astype(np.float32) * (360 / 255)

    gray = np.asarray(img.convert("L")).astype(np.float32) / 255
    edges = np.asarray(img.convert("L").filter(ImageFilter.FIND_EDGES)).astype(np.float32) / 255
    smooth = edges < 0.06

    H = img.size[1]
    lower = np.zeros_like(smooth)
    lower[int(H * 0.35):] = True
    blue_water = (hue > 170) & (hue < 255) & (sat > 0.12) & (val > 0.2)
    turbid = (hue > 20) & (hue < 50) & (sat > 0.25) & (sat < 0.65) & (val > 0.3) & (val < 0.75) & smooth
    water = (blue_water | turbid) & smooth
    water_frac = float(water[lower].mean()) if lower.any() else float(water.mean())
    fire = ((hue < 35) | (hue > 345)) & (sat > 0.6) & (val > 0.75)
    fire_frac = float(fire.mean())
    brown = (hue > 15) & (hue < 45) & (sat > 0.25) & (val < 0.65) & (edges > 0.08)
    debris_frac = float(brown.mean())
    grey_road = (sat < 0.12) & (val > 0.25) & (val < 0.7) & smooth & lower
    road_frac = float(grey_road.mean())
    straight = float(edges.mean())

    detected, scores = [], []
    if water_frac > 0.18:
        detected.append("Flood water")
        scores.append(min(1.0, water_frac / 0.6))
    if road_frac > 0.08 and (water_frac > 0.12 or debris_frac > 0.12):
        detected.append("Road blockage")
        scores.append(min(1.0, (road_frac + water_frac + debris_frac) / 0.8))
    if debris_frac > 0.10:
        detected.append("Debris")
        scores.append(min(1.0, debris_frac / 0.4))
    if fire_frac > 0.015:
        detected.append("Fire")
        scores.append(min(1.0, fire_frac / 0.08))
    if debris_frac > 0.22 and straight > 0.09:
        detected.append("Possible structural damage")
        scores.append(min(1.0, debris_frac / 0.5) * 0.8)
    sev_score = max(scores) if scores else 0.0
    severity = "High" if sev_score >= 0.66 else "Moderate" if sev_score >= 0.33 else "Low" if detected else "None detected"
    # confidence is deliberately capped: this is an untrained heuristic
    conf = round(min(0.72, 0.35 + 0.4 * sev_score), 2) if detected else 0.3
    return {
        "detected": detected, "estimated_severity": severity, "confidence": conf,
        "indicators": {"water_fraction": round(water_frac, 3), "fire_fraction": round(fire_frac, 3),
                       "debris_fraction": round(debris_frac, 3), "road_surface_fraction": round(road_frac, 3)},
        "model": MODEL_NAME, "model_version": MODEL_VERSION,
        "disclaimer": "Heuristic colour/texture analysis, not a trained model. No measurements (depth, area) are implied. Human verification required.",
    }
