"""Real satellite / terrain / land-cover retrieval from Microsoft Planetary Computer (anonymous, open data).

Sentinel-1 RTC (Copernicus Sentinel data, radiometrically terrain corrected), Sentinel-2 L2A, Copernicus DEM GLO-30, ESA WorldCover.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import numpy as np
from shapely.geometry import box, shape

from ..engines.geo import GridTransform
from .net import LiveDataError, sign, stac_search, warp_read

log = logging.getLogger("disha.live")


def _coverage(item: dict, bbox) -> float:
    try:
        b = box(*bbox)
        return float(shape(item["geometry"]).intersection(b).area / b.area)
    except Exception:
        return 0.0


def _dt(item: dict) -> datetime:
    return datetime.fromisoformat(item["properties"]["datetime"].replace("Z", "+00:00"))


def _d(x: date | str) -> date:
    return x if isinstance(x, date) else date.fromisoformat(str(x)[:10])


# ------------------------------------------------------------------ Sentinel-1
def pick_s1_pair(bbox, pre_end, post_start, post_end, pre_lookback_days: int = 75) -> tuple[dict, dict]:
    pre_end, post_start, post_end = _d(pre_end), _d(post_start), _d(post_end)
    pre = stac_search("sentinel-1-rtc", bbox, f"{pre_end - timedelta(days=pre_lookback_days)}/{pre_end}")
    post = stac_search("sentinel-1-rtc", bbox, f"{post_start}/{post_end}")
    pre = [i for i in pre if _coverage(i, bbox) >= 0.9]
    post = [i for i in post if _coverage(i, bbox) >= 0.9]
    if not pre or not post:
        raise LiveDataError(f"No Sentinel-1 RTC scene fully covering the area: {len(pre)} pre-event, {len(post)} post-event in the requested windows")
    best, best_score = None, 1e9
    for a in pre:
        for b in post:
            pa, pb = a["properties"], b["properties"]
            if pa.get("sat:relative_orbit") != pb.get("sat:relative_orbit") or pa.get("sat:orbit_state") != pb.get("sat:orbit_state"):
                continue  # compare like with like: same track and pass direction
            score = (pre_end - _dt(a).date()).days + (_dt(b).date() - post_start).days
            if score < best_score:
                best, best_score = (a, b), score
    if not best:
        raise LiveDataError("Sentinel-1 scenes exist but none share the same orbit track/direction before and after the event")
    return best


def read_s1_db(item: dict, t: GridTransform) -> np.ndarray:
    href = sign("sentinel-1-rtc", item["assets"]["vv"]["href"])
    lin = warp_read(href, t, "average")  # multilook in LINEAR power domain, then to dB
    lin[~(lin > 0)] = np.nan
    return (10 * np.log10(np.clip(lin, 1e-5, None))).astype(np.float32)


# ------------------------------------------------------------------ Sentinel-2
def pick_s2(bbox, start, end, max_cloud: float = 90.0, prefer_near=None) -> dict | None:
    items = stac_search("sentinel-2-l2a", bbox, f"{_d(start)}/{_d(end)}", query={"eo:cloud_cover": {"lt": max_cloud}})
    items = [i for i in items if _coverage(i, bbox) >= 0.9]
    if not items:
        return None
    near = _d(prefer_near) if prefer_near else None
    key = (lambda i: (i["properties"]["eo:cloud_cover"] + (abs((_dt(i).date() - near).days) * 1.5 if near else 0)))
    return min(items, key=key)


def read_s2(item: dict, t: GridTransform) -> dict:
    col = "sentinel-2-l2a"
    offset = 1000.0 if str(item["properties"].get("s2:processing_baseline", "00")) >= "04.00" else 0.0

    def band(name: str, res="average"):
        a = warp_read(sign(col, item["assets"][name]["href"]), t, res)
        return np.clip((a - offset) / 10000.0, 0, 1.5).astype(np.float32)

    b02, b03, b04, b08, b11, b12 = (band(n) for n in ("B02", "B03", "B04", "B08", "B11", "B12"))
    scl = warp_read(sign(col, item["assets"]["SCL"]["href"]), t, "nearest")
    bad = np.isin(scl, (3, 8, 9, 10, 11)) | ~np.isfinite(b08) | ~np.isfinite(b03)
    with np.errstate(invalid="ignore", divide="ignore"):
        ndwi = (b03 - b08) / (b03 + b08)
        ndvi = (b08 - b04) / (b08 + b04)
        nbr = (b08 - b12) / (b08 + b12)
    rgb = np.dstack([b04, b03, b02])
    rgb = (np.clip(np.nan_to_num(rgb) / 0.28, 0, 1) ** (1 / 1.3) * 255).astype(np.uint8)
    valid = np.isfinite(scl)
    cloud_pct = float(bad[valid].mean() * 100) if valid.any() else 100.0
    for a in (ndwi, ndvi, nbr):
        a[bad] = np.nan
    return {"ndwi": ndwi.astype(np.float32), "ndvi": ndvi.astype(np.float32), "nbr": nbr.astype(np.float32), "cloud": bad, "cloud_pct": cloud_pct, "rgb": rgb}


# ------------------------------------------------------------------ DEM + land cover
def read_dem(bbox, t: GridTransform) -> tuple[np.ndarray, dict]:
    items = stac_search("cop-dem-glo-30", bbox)
    if not items:
        raise LiveDataError("No Copernicus DEM tile for this area")
    out = np.full((t.height, t.width), np.nan, np.float32)
    for it in items:
        a = warp_read(sign("cop-dem-glo-30", it["assets"]["data"]["href"]), t, "bilinear")
        m = ~np.isfinite(out) & np.isfinite(a)
        out[m] = a[m]
    if not np.isfinite(out).any():
        raise LiveDataError("Copernicus DEM returned no valid pixels")
    fill = np.nanmedian(out)
    out = np.where(np.isfinite(out), out, fill).astype(np.float32)
    return out, {"items": [i["id"] for i in items]}


def read_worldcover(bbox, t: GridTransform) -> tuple[np.ndarray, dict]:
    items = stac_search("esa-worldcover", bbox, "2021-01-01/2021-12-31") or stac_search("esa-worldcover", bbox, "2020-01-01/2020-12-31")
    if not items:
        raise LiveDataError("No ESA WorldCover tile for this area")
    out = np.zeros((t.height, t.width), np.float32)
    for it in items:
        a = warp_read(sign("esa-worldcover", it["assets"]["map"]["href"]), t, "mode")
        out = np.where(np.isfinite(a) & (a > 0), a, out)
    return out.astype(np.int16), {"items": [i["id"] for i in items]}
