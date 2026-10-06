"""Detection evaluation against a registered ground-truth polygon set. Never invoked for synthetic demo data."""
from __future__ import annotations

import numpy as np
from shapely.geometry import shape

from ..services.pipeline import event_dir


def compute_metrics(pred: np.ndarray, truth: np.ndarray) -> dict:
    pred, truth = pred.astype(bool), truth.astype(bool)
    tp, fp = int((pred & truth).sum()), int((pred & ~truth).sum())
    fn, tn = int((~pred & truth).sum()), int((~pred & ~truth).sum())
    div = lambda a, b: round(a / b, 4) if b else None  # noqa: E731
    p, r = div(tp, tp + fp), div(tp, tp + fn)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "accuracy": div(tp + tn, tp + fp + fn + tn), "precision": p, "recall": r,
            "f1": div(2 * p * r, p + r) if p and r else None, "iou": div(tp, tp + fp + fn), "false_positive_rate": div(fp, fp + tn)}


def evaluate_event(event, geojson: dict) -> dict:
    import rasterio.features
    from rasterio.transform import from_bounds
    z = np.load(event_dir(event.id) / "rasters.npz")
    w, s, e, n = [float(x) for x in z["bounds"]]
    h, wd = z["mask"].shape
    feats = geojson["features"] if geojson.get("type") == "FeatureCollection" else [geojson]
    geoms = [shape(f["geometry"] if f.get("type") == "Feature" else f) for f in feats]
    truth = rasterio.features.rasterize([(g, 1) for g in geoms], out_shape=(h, wd), transform=from_bounds(w, s, e, n, wd, h), fill=0).astype(bool)
    m = compute_metrics(z["mask"], truth)
    m.update({"mean_confidence": float(z["confidence"][z["mask"]].mean()) if z["mask"].any() else None, "reference": "user-registered ground truth", "note": "Metrics apply to this event only."})
    return m
