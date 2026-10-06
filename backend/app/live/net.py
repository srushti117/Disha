"""Network helpers for LIVE data: STAC search, anonymous Planetary Computer signing, GDAL windowed warps, disk cache."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

import numpy as np
import requests

from ..core.config import get_settings
from ..engines.geo import GridTransform

log = logging.getLogger("disha.live")
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
UA = {"User-Agent": "DISHA-research/2.0 (disaster decision-support prototype)"}
_TOKENS: dict[str, tuple[float, str]] = {}


class LiveDataError(RuntimeError):
    """Raised when a required real dataset cannot be retrieved. Never papered over with simulated values."""


def cache_dir() -> Path:
    d = get_settings().data_dir / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_key(*parts) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def http_json(method: str, url: str, retries: int = 5, timeout: int = 60, **kw):
    last = None
    headers = {**UA, **kw.pop("headers", {})}
    for i in range(retries):
        try:
            r = requests.request(method, url, timeout=timeout, headers=headers, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                if r.status_code == 429:
                    time.sleep(6 * (i + 1))  # rate limited: back off harder
                raise RuntimeError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r.json()
        except Exception as e:  # retry with backoff
            last = e
            time.sleep(1.5 * (i + 1))
    raise LiveDataError(f"{url} failed after {retries} attempts: {last}")


def stac_search(collection: str, bbox, datetime_range: str | None = None, query: dict | None = None, limit: int = 50) -> list[dict]:
    body: dict = {"collections": [collection], "bbox": list(bbox), "limit": limit}
    if datetime_range:
        body["datetime"] = datetime_range
    if query:
        body["query"] = query
    return http_json("POST", f"{STAC}/search", json=body).get("features", [])


def sign(collection: str, href: str) -> str:
    """Anonymous signing. Sentinel collections use one cached collection token (1 request / 20 min); others sign per asset."""
    if collection in ("sentinel-1-rtc", "sentinel-2-l2a"):
        now = time.time()
        tok = _TOKENS.get(collection)
        if not tok or tok[0] < now:
            j = http_json("GET", f"https://planetarycomputer.microsoft.com/api/sas/v1/token/{collection}")
            tok = (now + 1200, j["token"])
            _TOKENS[collection] = tok
        return f"{href}?{tok[1]}"
    time.sleep(0.4)
    return http_json("GET", "https://planetarycomputer.microsoft.com/api/sas/v1/sign", params={"href": href})["href"]


def warp_read(href: str, t: GridTransform, resampling: str = "average", band: int = 1, dtype="float32") -> np.ndarray:
    """Read `href` resampled onto the event grid (EPSG:4326, north-up). Nodata becomes NaN. GDAL uses COG overviews."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.vrt import WarpedVRT

    dst = from_bounds(t.west, t.south, t.east, t.north, t.width, t.height)
    env = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff", GDAL_HTTP_MAX_RETRY="4",
               GDAL_HTTP_RETRY_DELAY="2", VSI_CACHE="TRUE", GDAL_HTTP_TIMEOUT="60")
    with rasterio.Env(**env):
        with rasterio.open(href) as ds:
            nod = ds.nodata
            with WarpedVRT(ds, crs="EPSG:4326", transform=dst, width=t.width, height=t.height, resampling=getattr(Resampling, resampling),
                           nodata=nod if nod is not None else 0) as vrt:
                a = vrt.read(band).astype(dtype)
                msk = vrt.read_masks(band) == 0
    a[msk] = np.nan
    return a
