"""Change detection abstraction.

ChangeDetectionEngine -> pluggable detectors:
  RuleBasedDetector      (BUILT)   SAR log-ratio + Otsu + indices + terrain/permanent-water masks
  RandomForestDetector   (BUILT, needs training; no bundled weights)
  SiameseUNetDetector    (ADAPTER) ONNX contract, weights not bundled
  ChangeFormerDetector   (ADAPTER) ONNX contract, weights not bundled

If a requested detector is unavailable the engine falls back to rule-based and says so in the result.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi

from ..core.config import get_settings

# ----------------------------------------------------------------------------- primitives


def db_to_lin(db):
    return np.power(10.0, np.asarray(db, dtype=np.float32) / 10.0)


def lin_to_db(lin):
    return 10.0 * np.log10(np.maximum(lin, 1e-6))


def speckle_filter(db: np.ndarray, size: int = 5) -> np.ndarray:
    """Boxcar multilook in the linear power domain (a simple stand-in for Lee/refined-Lee)."""
    lin = db_to_lin(db)
    filt = ndi.uniform_filter(lin, size=size, mode="reflect")
    return lin_to_db(filt)


def log_ratio(pre_db: np.ndarray, post_db: np.ndarray) -> np.ndarray:
    """10*log10(post/pre) == post_db - pre_db. Negative = backscatter drop (open water signature)."""
    return post_db - pre_db


def otsu_threshold(values: np.ndarray, bins: int = 256) -> tuple[float, float]:
    """Otsu's threshold. Returns (threshold, separability in [0,1] = between-class / total variance)."""
    v = values[np.isfinite(values)]
    if v.size < 50:
        return float("nan"), 0.0
    hist, edges = np.histogram(v, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist).astype(float)
    w1 = w0[-1] - w0
    s0 = np.cumsum(hist * centers)
    m0 = np.divide(s0, w0, out=np.zeros_like(s0), where=w0 > 0)
    m1 = np.divide(s0[-1] - s0, w1, out=np.zeros_like(s0), where=w1 > 0)
    between = w0 * w1 * (m0 - m1) ** 2
    near_max = np.flatnonzero(between >= 0.999 * between.max())
    k = int(near_max.mean())  # between-class variance is flat across an empty gap: use the plateau midpoint
    total_var = v.var() * v.size * v.size
    sep = float(between[k] / total_var) if total_var > 0 else 0.0
    return float(centers[k]), sep


def adaptive_threshold(
    values: np.ndarray, lo: float, hi: float, fallback: float, min_separability: float = 0.25
) -> tuple[float, str]:
    """Otsu accepted only if bimodal enough and within physically plausible bounds; else documented fallback."""
    t, sep = otsu_threshold(values)
    if np.isfinite(t) and sep >= min_separability and lo <= t <= hi:
        return t, f"otsu(sep={sep:.2f})"
    return fallback, f"fallback(otsu={t:.2f}, sep={sep:.2f})" if np.isfinite(t) else "fallback(no-data)"


def remove_small(mask: np.ndarray, min_px: int) -> np.ndarray:
    lab, n = ndi.label(mask)
    if n == 0:
        return mask
    sizes = ndi.sum(mask, lab, index=np.arange(1, n + 1))
    keep = np.zeros(n + 1, dtype=bool)
    keep[1:] = sizes >= min_px
    return keep[lab]


def local_fraction(mask: np.ndarray, size: int = 7) -> np.ndarray:
    return ndi.uniform_filter(mask.astype(np.float32), size=size, mode="reflect")


# ----------------------------------------------------------------------------- contracts


@dataclass
class DetectionInputs:
    hazard: str
    pre_sar_db: np.ndarray | None = None
    post_sar_db: np.ndarray | None = None
    pre_ndvi: np.ndarray | None = None
    post_ndvi: np.ndarray | None = None
    pre_ndwi: np.ndarray | None = None
    post_ndwi: np.ndarray | None = None
    pre_nbr: np.ndarray | None = None
    post_nbr: np.ndarray | None = None
    cloud_mask: np.ndarray | None = None  # True where post optical is cloud-covered
    quality_mask: np.ndarray | None = None  # True where SAR observation is usable (not shadow/layover/nodata)
    dem: np.ndarray | None = None
    slope_deg: np.ndarray | None = None
    builtup: np.ndarray | None = None
    coast_dist_m: np.ndarray | None = None
    hotspots: list[dict] = field(default_factory=list)  # VIIRS: lat, lon, frp, confidence
    transform: object | None = None
    optical_weight: float = 0.0
    pixel_size_m: float = 30.0

    @property
    def shape(self):
        for a in (self.post_sar_db, self.post_ndvi, self.post_nbr):
            if a is not None:
                return a.shape
        raise ValueError("no raster inputs")


@dataclass
class DetectionResult:
    hazard: str
    mask: np.ndarray  # bool
    severity: np.ndarray  # float32 0..1
    confidence: np.ndarray  # float32 0..1 (per-pixel; meaningful where mask)
    model_name: str
    model_version: str
    stats: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)  # hazard-specific outputs (burn_area, hotspots, surge...)
    extra_layers: dict[str, np.ndarray] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------- detectors


class BaseDetector(ABC):
    name = "base"
    version = "0"
    kind = "rule"
    hazards: tuple[str, ...] = ()

    def is_available(self) -> tuple[bool, str]:
        return True, "ok"

    @abstractmethod
    def detect(self, inputs: DetectionInputs) -> DetectionResult: ...


class RuleBasedDetector(BaseDetector):
    name = "disha-rule-based"
    version = "1.0.0"
    kind = "rule"
    hazards = ("flood", "wildfire", "landslide", "cyclone")

    def detect(self, inputs: DetectionInputs) -> DetectionResult:
        from . import hazards

        fn = hazards.RULES.get(inputs.hazard)
        if fn is None:
            raise ValueError(f"No rule module for hazard '{inputs.hazard}'")
        res = fn(inputs)
        res.model_name, res.model_version = self.name, self.version
        return res


def _features(inp: DetectionInputs) -> np.ndarray:
    pre, post = inp.pre_sar_db, inp.post_sar_db
    lr = log_ratio(speckle_filter(pre), speckle_filter(post))
    cols = [lr, speckle_filter(post), speckle_filter(pre)]
    cols.append(inp.slope_deg if inp.slope_deg is not None else np.zeros_like(lr))
    if inp.post_ndvi is not None and inp.pre_ndvi is not None:
        cols.append(np.nan_to_num(inp.pre_ndvi - inp.post_ndvi, nan=0.0))
    else:
        cols.append(np.zeros_like(lr))
    return np.stack([c.astype(np.float32).ravel() for c in cols], axis=1)


class RandomForestDetector(BaseDetector):
    """Per-pixel Random Forest on SAR/terrain/index features. Trainable; no weights ship with the repo."""

    name = "disha-random-forest"
    version = "0.1.0"
    kind = "ml"
    hazards = ("flood", "landslide", "wildfire", "cyclone")

    def __init__(self, hazard: str = "flood"):
        self.hazard = hazard
        self.path = get_settings().models_dir / f"rf_{hazard}.joblib"
        self._model = None

    def is_available(self):
        if not self.path.exists():
            return False, f"No trained Random Forest at {self.path.name}. Train with RandomForestDetector.fit()."
        return True, "ok"

    def fit(self, inputs: DetectionInputs, truth_mask: np.ndarray, n_estimators: int = 60, max_samples: int = 60_000):
        import joblib
        from sklearn.ensemble import RandomForestClassifier

        X, y = _features(inputs), truth_mask.ravel().astype(int)
        idx = np.random.default_rng(0).choice(len(y), size=min(max_samples, len(y)), replace=False)
        clf = RandomForestClassifier(n_estimators=n_estimators, n_jobs=-1, random_state=0, class_weight="balanced")
        clf.fit(X[idx], y[idx])
        joblib.dump(clf, self.path)
        self._model = clf
        return clf

    def detect(self, inputs: DetectionInputs) -> DetectionResult:
        import joblib

        ok, why = self.is_available()
        if not ok:
            raise RuntimeError(why)
        clf = self._model or joblib.load(self.path)
        p = clf.predict_proba(_features(inputs))[:, 1].reshape(inputs.shape).astype(np.float32)
        mask = p > 0.5
        return DetectionResult(
            inputs.hazard, mask, np.where(mask, p, 0).astype(np.float32), np.abs(2 * p - 1).astype(np.float32),
            self.name, self.version, stats={"method": "random_forest"},
        )


class _OnnxDetector(BaseDetector):
    """Contract: ONNX model with inputs `pre`,`post` (1,C,H,W float32, per-channel standardised) and output
    `change` (1,1,H,W) probabilities. Weights are NOT bundled; drop `<file>` into models/ to enable."""

    file = ""
    kind = "dl"
    hazards = ("flood", "cyclone", "landslide", "wildfire")
    tile = 256

    def is_available(self):
        path = get_settings().models_dir / self.file
        if not path.exists():
            return False, f"{self.name}: weights '{self.file}' not found in models/ (adapter only)."
        try:
            import onnxruntime  # noqa: F401
        except Exception:
            return False, f"{self.name}: onnxruntime not installed."
        return True, "ok"

    def detect(self, inputs: DetectionInputs) -> DetectionResult:
        import onnxruntime as ort

        ok, why = self.is_available()
        if not ok:
            raise RuntimeError(why)
        sess = ort.InferenceSession(str(get_settings().models_dir / self.file))

        def stack(sar, ndvi):
            ch = [np.nan_to_num(sar, nan=-15.0)]
            ch.append(np.nan_to_num(ndvi, nan=0.0) if ndvi is not None else np.zeros_like(ch[0]))
            a = np.stack(ch).astype(np.float32)
            return (a - a.mean(axis=(1, 2), keepdims=True)) / (a.std(axis=(1, 2), keepdims=True) + 1e-6)

        pre, post = stack(inputs.pre_sar_db, inputs.pre_ndvi), stack(inputs.post_sar_db, inputs.post_ndvi)
        H, W = inputs.shape
        prob = np.zeros((H, W), np.float32)
        T = self.tile
        for r in range(0, H, T):
            for c in range(0, W, T):
                a, b = pre[:, r : r + T, c : c + T], post[:, r : r + T, c : c + T]
                ph, pw = T - a.shape[1], T - a.shape[2]
                a, b = np.pad(a, ((0, 0), (0, ph), (0, pw))), np.pad(b, ((0, 0), (0, ph), (0, pw)))
                out = sess.run(["change"], {"pre": a[None], "post": b[None]})[0][0, 0]
                prob[r : r + T, c : c + T] = out[: T - ph, : T - pw]
        mask = prob > 0.5
        return DetectionResult(
            inputs.hazard, mask, np.where(mask, prob, 0).astype(np.float32), np.abs(2 * prob - 1),
            self.name, self.version, stats={"method": "onnx"},
        )


class SiameseUNetDetector(_OnnxDetector):
    name, version, file = "siamese-unet", "adapter-0.1", "siamese_unet.onnx"


class ChangeFormerDetector(_OnnxDetector):
    name, version, file = "changeformer", "adapter-0.1", "changeformer.onnx"


# ----------------------------------------------------------------------------- engine


class ChangeDetectionEngine:
    def __init__(self):
        self.default = RuleBasedDetector()

    def registry(self, hazard: str = "flood") -> dict[str, BaseDetector]:
        return {
            "rule_based": self.default,
            "random_forest": RandomForestDetector(hazard),
            "siamese_unet": SiameseUNetDetector(),
            "changeformer": ChangeFormerDetector(),
        }

    def availability(self, hazard: str = "flood") -> list[dict]:
        out = []
        for key, d in self.registry(hazard).items():
            ok, why = d.is_available()
            out.append({"key": key, "name": d.name, "version": d.version, "kind": d.kind, "available": ok, "detail": why})
        return out

    def detect(self, inputs: DetectionInputs, prefer: str = "rule_based") -> DetectionResult:
        det = self.registry(inputs.hazard).get(prefer, self.default)
        ok, why = det.is_available()
        note = None
        if not ok:
            note = f"Requested detector '{det.name}' unavailable ({why}). Fell back to {self.default.name}."
            det = self.default
        try:
            res = det.detect(inputs)
        except Exception as e:  # never silently swallow: record and fall back
            if det is self.default:
                raise
            note = f"Detector '{det.name}' failed ({e}). Fell back to {self.default.name}."
            res = self.default.detect(inputs)
        if note:
            res.notes.append(note)
        return res
