"""Population: WorldPop 2020 (1 km, UN-adjusted aggregate) disaggregated to built-up pixels with ESA WorldCover (dasymetric mapping).

Result is a MODELLED ESTIMATE, not a census. Totals per 1 km cell match WorldPop; the within-cell distribution follows built-up land cover.
"""
from __future__ import annotations

import logging
import math

import numpy as np
import requests

from ..engines.geo import GridTransform
from .net import LiveDataError, UA, cache_dir, http_json

log = logging.getLogger("disha.live")
WP_URL = "https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/2020/{iso}/{iso_l}_ppp_2020_1km_Aggregated.tif"


A2_TO_A3 = {"IN": "IND", "BD": "BGD", "NP": "NPL", "PK": "PAK", "LK": "LKA", "BT": "BTN", "MM": "MMR", "TH": "THA", "VN": "VNM", "KH": "KHM", "LA": "LAO", "ID": "IDN", "PH": "PHL",
            "MY": "MYS", "CN": "CHN", "JP": "JPN", "KR": "KOR", "AF": "AFG", "IR": "IRN", "IQ": "IRQ", "TR": "TUR", "US": "USA", "MX": "MEX", "BR": "BRA", "CO": "COL", "PE": "PER",
            "CL": "CHL", "AR": "ARG", "EC": "ECU", "HT": "HTI", "CU": "CUB", "DO": "DOM", "GT": "GTM", "HN": "HND", "AU": "AUS", "NZ": "NZL", "FJ": "FJI", "PG": "PNG", "ZA": "ZAF",
            "MZ": "MOZ", "MW": "MWI", "ZW": "ZWE", "ZM": "ZMB", "MG": "MDG", "KE": "KEN", "ET": "ETH", "SO": "SOM", "SD": "SDN", "SS": "SSD", "NG": "NGA", "NE": "NER", "GH": "GHA",
            "SN": "SEN", "ML": "MLI", "TD": "TCD", "CD": "COD", "TZ": "TZA", "UG": "UGA", "RW": "RWA", "MA": "MAR", "DZ": "DZA", "EG": "EGY", "ES": "ESP", "PT": "PRT", "FR": "FRA",
            "IT": "ITA", "DE": "DEU", "GB": "GBR", "GR": "GRC", "RO": "ROU", "UA": "UKR", "PL": "POL", "CA": "CAN"}


def country_iso3(lat: float, lon: float) -> str | None:
    p = cache_dir() / f"iso_{round(lat, 1)}_{round(lon, 1)}.txt"
    if p.exists():
        return p.read_text().strip() or None
    try:
        j = http_json("GET", "https://nominatim.openstreetmap.org/reverse", params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 3})
        iso = A2_TO_A3.get(j["address"]["country_code"].upper())
        if iso:
            p.write_text(iso)
        return iso
    except Exception as e:
        log.warning("country lookup failed: %s", e)
        return None


def worldpop_path(iso: str):
    p = cache_dir() / f"worldpop_{iso}_2020_1km.tif"
    if p.exists() and p.stat().st_size > 10_000:
        return p
    url = WP_URL.format(iso=iso, iso_l=iso.lower())
    tmp = p.with_suffix(".part")
    try:
        with requests.get(url, stream=True, timeout=120, headers=UA) as r:
            if r.status_code != 200:
                raise LiveDataError(f"WorldPop file not available for {iso} (HTTP {r.status_code})")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        tmp.rename(p)
    except LiveDataError:
        raise
    except Exception as e:
        raise LiveDataError(f"WorldPop download failed: {e}") from e
    return p


def disaggregate(coarse_per_pixel: np.ndarray, parent_id: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """People per fine pixel: parent total (carried in `coarse_per_pixel`) x weight / sum(weights of that parent's pixels). Pure + unit-tested."""
    ok = (parent_id >= 0) & np.isfinite(coarse_per_pixel) & (coarse_per_pixel > 0)
    ids = parent_id[ok]
    uniq, inv = np.unique(ids, return_inverse=True)
    wsum = np.bincount(inv, weights=weights[ok])
    parent_total = np.zeros(len(uniq))
    parent_total[inv] = coarse_per_pixel[ok]
    out = np.zeros_like(coarse_per_pixel, dtype=np.float32)
    w = weights[ok]
    out[ok] = (parent_total[inv] * np.divide(w, wsum[inv], out=np.zeros_like(w), where=wsum[inv] > 0)).astype(np.float32)
    return out


def population_grid(t: GridTransform, builtup_ext: np.ndarray, water_ext: np.ndarray, t_ext: GridTransform, iso: str, crop: tuple[slice, slice]) -> tuple[np.ndarray, dict]:
    """t_ext: grid padded by ~1.5 km so border parent cells are normalised correctly; crop: slices cutting t_ext back to t."""
    import rasterio
    from rasterio.windows import from_bounds

    path = worldpop_path(iso)
    with rasterio.open(path) as ds:
        win = from_bounds(t_ext.west, t_ext.south, t_ext.east, t_ext.north, ds.transform).round_offsets().round_lengths()
        win = win.__class__(win.col_off - 1, win.row_off - 1, win.width + 2, win.height + 2)
        coarse = ds.read(1, window=win, boundless=True, fill_value=np.nan).astype(np.float64)
        tr = ds.window_transform(win)
        nod = ds.nodata
    if nod is not None:
        coarse[coarse == nod] = np.nan
    coarse[coarse < 0] = np.nan
    lon, lat = t_ext.pixel_centers()
    col = np.floor((lon - tr.c) / tr.a).astype(int)
    row = np.floor((lat - tr.f) / tr.e).astype(int)
    inside = (row >= 0) & (row < coarse.shape[0]) & (col >= 0) & (col < coarse.shape[1])
    parent = np.where(inside, row * coarse.shape[1] + col, -1)
    per_pixel = np.full(lon.shape, np.nan)
    per_pixel[inside] = coarse[row[inside], col[inside]]
    w = np.where(builtup_ext, 1.0, 0.04)
    w = np.where(water_ext, 0.0, w)
    pop_ext = disaggregate(per_pixel, parent, w.astype(np.float64))
    pop = pop_ext[crop]
    return pop, {"source": "WorldPop 2020 1 km (UN-adjusted) disaggregated with ESA WorldCover built-up", "iso3": iso, "total": float(np.nansum(pop)), "estimate": True}
