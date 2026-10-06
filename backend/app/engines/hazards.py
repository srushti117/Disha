"""Hazard-aware rule modules used by RuleBasedDetector.

Each function takes DetectionInputs and returns a DetectionResult with per-pixel mask/severity/confidence.
Thresholds are adaptive (Otsu) with documented fallbacks, and every mask applied is recorded in `stats`.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi

from .change_detection import (
    DetectionInputs,
    DetectionResult,
    adaptive_threshold,
    local_fraction,
    log_ratio,
    remove_small,
    speckle_filter,
)


def _px_area_km2(inp: DetectionInputs) -> float:
    dx, dy = inp.transform.pixel_size_m if inp.transform is not None else (inp.pixel_size_m, inp.pixel_size_m)
    return dx * dy / 1e6


def _valid(inp: DetectionInputs, *arrs) -> np.ndarray:
    v = np.ones(inp.shape, bool) if inp.quality_mask is None else inp.quality_mask.copy()
    for a in arrs:
        if a is not None:
            v &= np.isfinite(a)
    return v


def _optical_avail(inp: DetectionInputs, *arrs) -> np.ndarray:
    ok = np.ones(inp.shape, bool)
    for a in arrs:
        if a is None:
            return np.zeros(inp.shape, bool)
        ok &= np.isfinite(a)
    if inp.cloud_mask is not None:
        ok &= ~inp.cloud_mask
    return ok


# --------------------------------------------------------------------------- FLOOD


def detect_flood(inp: DetectionInputs) -> DetectionResult:
    pre, post = speckle_filter(inp.pre_sar_db), speckle_filter(inp.post_sar_db)
    lr = log_ratio(pre, post)
    valid = _valid(inp, lr)
    slope = inp.slope_deg if inp.slope_deg is not None else np.zeros(inp.shape, np.float32)
    notes: list[str] = []

    sig_r = 1.4826 * float(np.nanmedian(np.abs(lr[valid] - np.nanmedian(lr[valid])))) if valid.any() else 1.0
    fb = -float(np.clip(3.5 * sig_r, 2.5, 5.0))  # fallback scales with the scene's own noise (robust sigma of the log-ratio)
    thr_lr, lr_method = adaptive_threshold(lr[valid], lo=-9.0, hi=-2.0, fallback=fb)
    thr_post, post_method = adaptive_threshold(post[valid], lo=-20.0, hi=-13.0, fallback=-15.5)

    perm_water = valid & (pre < thr_post)  # already dark before the event
    terrain_ok = slope < 5.0  # water cannot pond on steep slopes (also removes radar shadow)
    cand = valid & (lr < thr_lr) & (post < thr_post) & ~perm_water & terrain_ok
    cand = ndi.binary_closing(cand, iterations=1)
    px_km2 = _px_area_km2(inp)
    min_px = max(6, int(0.005 / px_km2))  # ~0.5 ha
    before = int(cand.sum())
    flood = remove_small(cand, min_px)
    removed_small = before - int(flood.sum())

    # urban double-bounce: flooded streets brighten SAR; weak, capped evidence
    urban_px = np.zeros(inp.shape, bool)
    if inp.builtup is not None:
        urban_px = valid & inp.builtup & (lr > 2.0) & (slope < 2.0) & ~flood
        urban_px = remove_small(urban_px, max(10, min_px))
        if urban_px.any():
            notes.append("Urban double-bounce rule flagged possible street flooding (low-confidence evidence).")

    # optical (SAR-first; optical only on cloud-free pixels)
    opt = _optical_avail(inp, inp.pre_ndwi, inp.post_ndwi)
    dndwi = np.nan_to_num(inp.post_ndwi - inp.pre_ndwi, nan=0.0) if inp.post_ndwi is not None else np.zeros(inp.shape)
    opt_flood = opt & (dndwi > 0.25) & (np.nan_to_num(inp.post_ndwi, nan=-1) > 0.0) if inp.post_ndwi is not None else np.zeros(inp.shape, bool)
    opt_only = opt_flood & ~flood & valid & ~perm_water & terrain_ok & (lr < -2.0) & (inp.optical_weight > 0)
    opt_only = remove_small(opt_only, min_px)
    mask = flood | opt_only | urban_px

    # severity: backscatter-drop intensity + DEM-based relative depth proxy (uncalibrated, not metres)
    drop = np.clip((-lr - 3.0) / 9.0, 0, 1)
    depth_term = np.zeros(inp.shape, np.float32)
    ws = None
    if inp.dem is not None and flood.sum() > 20:
        ws = float(np.percentile(inp.dem[flood & (slope < 2.0)], 90)) if (flood & (slope < 2.0)).sum() > 20 else float(np.percentile(inp.dem[flood], 90))
        depth_term = np.clip((ws - inp.dem) / 3.0, 0, 1).astype(np.float32)
    severity = np.where(flood, 0.6 * drop + 0.4 * depth_term, 0).astype(np.float32)
    severity = np.where(opt_only, np.maximum(severity, 0.25), severity)
    severity = np.where(urban_px, 0.45, severity).astype(np.float32)

    # confidence
    sigma = float(np.std(lr[valid & ~flood & ~perm_water])) if (valid & ~flood & ~perm_water).sum() > 100 else 1.0
    sigma = max(sigma, 0.3)
    conf_sar = 0.55 + 0.45 * np.tanh(np.clip(thr_lr - lr, 0, None) / (2 * sigma))
    neigh = local_fraction(flood, 7)
    conf = conf_sar * (0.7 + 0.3 * neigh)
    a = min(1.0, inp.optical_weight * 2)
    agree = flood & opt & opt_flood
    disagree = flood & opt & ~opt_flood
    conf = np.where(agree, conf + (1 - conf) * 0.5 * a, conf)
    conf = np.where(disagree, conf * (1 - 0.35 * a), conf)
    conf = conf * (1 - np.clip((slope - 2.0) / 10.0, 0, 0.3))
    conf = np.where(opt_only, 0.5, conf)
    conf = np.where(urban_px, 0.4, conf)
    conf = np.clip(np.where(mask, conf, 0), 0, 0.99).astype(np.float32)

    stats = {
        "method": "SAR log-ratio + adaptive threshold (Otsu) + terrain/permanent-water masks",
        "log_ratio_threshold_db": round(float(thr_lr), 2), "log_ratio_threshold_method": lr_method,
        "water_backscatter_threshold_db": round(float(thr_post), 2), "water_threshold_method": post_method,
        "noise_sigma_db": round(sigma, 2),
        "permanent_water_km2": round(float(perm_water.sum() * px_km2), 3),
        "terrain_masked_km2": round(float((~terrain_ok).sum() * px_km2), 3),
        "small_blobs_removed_px": removed_small,
        "optical_agree_fraction": round(float(agree.sum() / max(1, (flood & opt).sum())), 3) if (flood & opt).any() else None,
        "optical_pixels_used_pct": round(float(opt.mean() * 100), 1),
        "water_surface_elev_m": round(ws, 2) if ws is not None else None,
        "severity_definition": "0.6*backscatter-drop index + 0.4*DEM relative-depth proxy (uncalibrated; not depth in metres)",
        "limitations": ["Flooded built-up areas often brighten SAR (double bounce) and may be under-detected.",
                        "Flooded vegetation can be missed in VV; consider VH/coherence in a production setting."],
    }
    return DetectionResult(
        "flood", mask, severity, conf, "", "", stats,
        outputs={"flood_area_km2": round(float(mask.sum() * px_km2), 3), "permanent_water_km2": stats["permanent_water_km2"]},
        extra_layers={"permanent_water": perm_water, "depth_proxy": depth_term}, notes=notes,
    )


# --------------------------------------------------------------------------- WILDFIRE


def detect_wildfire(inp: DetectionInputs) -> DetectionResult:
    px_km2 = _px_area_km2(inp)
    opt = _optical_avail(inp, inp.pre_nbr, inp.post_nbr)
    dnbr = np.where(opt, inp.pre_nbr - inp.post_nbr, np.nan) if inp.pre_nbr is not None else np.full(inp.shape, np.nan)
    thr, method = adaptive_threshold(dnbr[np.isfinite(dnbr)], lo=0.10, hi=0.45, fallback=0.15) if np.isfinite(dnbr).any() else (0.15, "fallback(no-optical)")
    burned = np.isfinite(dnbr) & (dnbr > thr)
    burned = remove_small(ndi.binary_closing(burned, iterations=1), 8)

    # SAR: weak all-weather support for cloud-covered pixels next to confirmed burn scars / hotspots
    sar_chg = np.zeros(inp.shape, np.float32)
    if inp.pre_sar_db is not None and inp.post_sar_db is not None:
        sar_chg = np.abs(speckle_filter(inp.post_sar_db) - speckle_filter(inp.pre_sar_db))

    active = np.zeros(inp.shape, bool)
    spots = []
    if inp.transform is not None:
        t = inp.transform
        dx, _ = t.pixel_size_m
        rad = max(1, int(round(375.0 / dx / 2)))
        for h in inp.hotspots:
            r, c = t.lonlat_to_rc(h["lon"], h["lat"])
            r, c = int(r), int(c)
            if 0 <= r < t.height and 0 <= c < t.width:
                active[max(0, r - rad) : r + rad + 1, max(0, c - rad) : c + rad + 1] = True
                spots.append({"lat": h["lat"], "lon": h["lon"], "frp_mw": h.get("frp"), "confidence": h.get("confidence")})
    near_evidence = ndi.binary_dilation(burned | active, iterations=6)
    probable = (~opt) & near_evidence & (sar_chg > 2.0) & _valid(inp)
    probable = remove_small(probable, 8)
    mask = burned | probable | active

    sev = np.where(burned, np.clip(np.nan_to_num(dnbr) / 1.0, 0, 1), 0)
    sev = np.where(probable, np.maximum(sev, 0.35), sev)
    sev = np.where(active, np.maximum(sev, 0.8), sev).astype(np.float32)
    near_hot = ndi.binary_dilation(active, iterations=int(max(2, 2000 / max(inp.pixel_size_m, 1))))
    conf = 0.6 + 0.4 * np.tanh(np.clip(np.nan_to_num(dnbr) - thr, 0, None) / 0.15)
    conf = np.where(near_hot & burned, np.minimum(conf + 0.12, 0.99), conf)
    conf = np.where(probable, 0.45, conf)
    conf = np.where(active & ~burned, np.maximum(conf, 0.7), conf)
    conf = np.clip(np.where(mask, conf, 0), 0, 0.99).astype(np.float32)

    return DetectionResult(
        "wildfire", mask, sev, conf, "", "",
        stats={"method": "dNBR (Sentinel-2) + VIIRS hotspots + SAR support under cloud", "dnbr_threshold": round(float(thr), 3),
               "dnbr_threshold_method": method, "optical_pixels_used_pct": round(float(opt.mean() * 100), 1)},
        outputs={"burn_area_km2": round(float(burned.sum() * px_km2), 3), "probable_burn_area_km2": round(float(probable.sum() * px_km2), 3),
                 "fire_severity": round(float(sev[mask].mean()), 3) if mask.any() else 0.0,
                 "hotspot_locations": spots[:100], "hotspot_count": len(spots)},
        extra_layers={"dnbr": np.nan_to_num(dnbr)},
    )


# --------------------------------------------------------------------------- LANDSLIDE


def detect_landslide(inp: DetectionInputs) -> DetectionResult:
    px_km2 = _px_area_km2(inp)
    slope = inp.slope_deg if inp.slope_deg is not None else np.zeros(inp.shape, np.float32)
    opt = _optical_avail(inp, inp.pre_ndvi, inp.post_ndvi)
    dndvi = np.where(opt, inp.pre_ndvi - inp.post_ndvi, 0.0)
    sar = np.abs(speckle_filter(inp.post_sar_db) - speckle_filter(inp.pre_sar_db)) if inp.post_sar_db is not None else np.zeros(inp.shape)
    a = np.clip((dndvi - 0.1) / 0.5, 0, 1)
    b = np.clip((slope - 12.0) / 30.0, 0, 1)
    c = np.clip((sar - 1.5) / 5.0, 0, 1)
    z = 3.2 * a + 2.2 * b + 2.8 * c - 3.0 + np.where(opt, 0.0, 0.9)  # no optical term available: bias compensates, confidence is reduced below
    p = (1 / (1 + np.exp(-z))).astype(np.float32)
    valid = _valid(inp)
    scar = valid & (p > 0.55) & (slope > 8) & ((a > 0.2) | (c > 0.35))
    scar = remove_small(ndi.binary_closing(scar, iterations=1), 6)

    # debris/run-out: downslope of scars, still showing SAR change
    debris = np.zeros(inp.shape, bool)
    if inp.dem is not None and scar.any():
        halo = ndi.binary_dilation(scar, iterations=max(14, int(1800 / max(inp.pixel_size_m, 1)))) & ~scar
        debris = halo & (inp.dem < np.percentile(inp.dem[scar], 50)) & (c > 0.25) & (slope < 25) & valid
        debris = remove_small(debris, 6)
    mask = scar | debris

    sev = np.where(scar, np.clip(0.5 * a + 0.3 * c + 0.2 * b + 0.15, 0, 1), 0)
    sev = np.where(debris, np.maximum(sev, 0.5), sev).astype(np.float32)
    evid = ((a > 0.3).astype(float) + (c > 0.3) + (b > 0.3)) / 3.0
    conf = np.clip(0.35 + 0.35 * p + 0.3 * evid, 0, 0.99)
    conf = np.where(~opt, conf * 0.85, conf)
    conf = np.where(debris & ~scar, conf * 0.8, conf)
    conf = np.where(mask, conf, 0).astype(np.float32)
    return DetectionResult(
        "landslide", mask, sev, conf, "", "",
        stats={"method": "Weighted dNDVI + slope + SAR change -> logistic probability", "optical_pixels_used_pct": round(float(opt.mean() * 100), 1),
               "scar_km2": round(float(scar.sum() * px_km2), 3), "debris_km2": round(float(debris.sum() * px_km2), 3)},
        outputs={"landslide_area_km2": round(float(mask.sum() * px_km2), 3),
                 "max_landslide_probability": round(float(p[mask].max()), 3) if mask.any() else 0.0},
        extra_layers={"landslide_probability": p, "debris": debris},
    )


# --------------------------------------------------------------------------- CYCLONE


def detect_cyclone(inp: DetectionInputs) -> DetectionResult:
    px_km2 = _px_area_km2(inp)
    pre, post = speckle_filter(inp.pre_sar_db), speckle_filter(inp.post_sar_db)
    sar = np.abs(post - pre)
    opt = _optical_avail(inp, inp.pre_ndvi, inp.post_ndvi)
    dndvi = np.where(opt, inp.pre_ndvi - inp.post_ndvi, 0.0)
    veg = np.clip((dndvi - 0.1) / 0.5, 0, 1)
    sarn = np.clip((sar - 1.5) / 6.0, 0, 1)
    built = inp.builtup if inp.builtup is not None else np.zeros(inp.shape, bool)
    roof = np.where(built, np.clip((sar - 2.0) / 6.0, 0, 1), 0)
    coast = inp.coast_dist_m if inp.coast_dist_m is not None else np.full(inp.shape, 1e9)
    dem = inp.dem if inp.dem is not None else np.zeros(inp.shape)
    surge = (post < -15) & (pre > -12) & (coast < 6000) & (dem < 8)
    surge = remove_small(surge, 8)
    base = np.where(opt, 0.45 * sarn + 0.55 * veg, 0.9 * sarn)
    damage = np.clip(np.maximum.reduce([base, roof, surge * 0.9]), 0, 1).astype(np.float32)
    valid = _valid(inp)
    mask = valid & (damage > 0.35)
    mask = remove_small(mask, 8)
    n_sources = (sarn > 0.3).astype(float) + (veg > 0.3) + surge
    conf = np.clip(0.4 + 0.2 * n_sources + 0.2 * damage, 0, 0.99)
    conf = np.where(~opt, conf * 0.9, conf)
    conf = np.where(mask, conf, 0).astype(np.float32)
    return DetectionResult(
        "cyclone", mask, np.where(mask, damage, 0).astype(np.float32), conf, "", "",
        stats={"method": "SAR change + dNDVI + built-up roof proxy + coastal surge rule", "optical_pixels_used_pct": round(float(opt.mean() * 100), 1)},
        outputs={"damage_score": round(float(damage[mask].mean()), 3) if mask.any() else 0.0,
                 "vegetation_damage": round(float(veg[mask].mean()), 3) if mask.any() else 0.0,
                 "surge_indicator": round(float(surge.sum() * px_km2), 3),
                 "damaged_area_km2": round(float(mask.sum() * px_km2), 3)},
        extra_layers={"surge": surge},
    )


RULES = {"flood": detect_flood, "wildfire": detect_wildfire, "landslide": detect_landslide, "cyclone": detect_cyclone}
