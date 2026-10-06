"""Geospatial helpers: raster<->lon/lat transform, H3 gridding, zonal aggregation, distances."""
from __future__ import annotations

import math
from dataclasses import dataclass

import h3
import numpy as np
from shapely.geometry import Polygon, mapping, shape

EARTH_R = 6_371_008.8


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class GridTransform:
    """Axis-aligned lon/lat raster (north-up). bounds = (west, south, east, north)."""

    west: float
    south: float
    east: float
    north: float
    height: int
    width: int

    @property
    def bounds(self):
        return (self.west, self.south, self.east, self.north)

    @property
    def center(self):
        return ((self.south + self.north) / 2, (self.west + self.east) / 2)

    @property
    def pixel_size_m(self) -> tuple[float, float]:
        lat = (self.south + self.north) / 2
        dx = (self.east - self.west) * 111_320 * math.cos(math.radians(lat)) / self.width
        dy = (self.north - self.south) * 110_574 / self.height
        return dx, dy

    def lonlat_to_rc(self, lon, lat):
        col = (np.asarray(lon) - self.west) / (self.east - self.west) * self.width
        row = (self.north - np.asarray(lat)) / (self.north - self.south) * self.height
        return row, col

    def rc_to_lonlat(self, row, col):
        lon = self.west + (np.asarray(col) + 0.5) / self.width * (self.east - self.west)
        lat = self.north - (np.asarray(row) + 0.5) / self.height * (self.north - self.south)
        return lon, lat

    def pixel_centers(self):
        rr, cc = np.meshgrid(np.arange(self.height), np.arange(self.width), indexing="ij")
        return self.rc_to_lonlat(rr, cc)

    def sample(self, arr: np.ndarray, lon, lat, default=np.nan):
        row, col = self.lonlat_to_rc(lon, lat)
        r = np.floor(row).astype(int)
        c = np.floor(col).astype(int)
        ok = (r >= 0) & (r < self.height) & (c >= 0) & (c < self.width)
        out = np.full(np.shape(r), default, dtype=float)
        out[ok] = arr[r[ok], c[ok]]
        return out

    @staticmethod
    def for_bounds(bounds, target_px_m: float = 30.0, max_px: int = 512) -> "GridTransform":
        w, s, e, n = bounds
        lat = (s + n) / 2
        width_m = (e - w) * 111_320 * math.cos(math.radians(lat))
        height_m = (n - s) * 110_574
        width = int(min(max_px, max(32, round(width_m / target_px_m))))
        height = int(min(max_px, max(32, round(height_m / target_px_m))))
        return GridTransform(w, s, e, n, height, width)


def polygon_bounds(geojson: dict) -> tuple[float, float, float, float]:
    return shape(geojson).bounds


def polygon_area_km2(geojson: dict) -> float:
    g = shape(geojson)
    lat = g.centroid.y
    kx, ky = 111.32 * math.cos(math.radians(lat)), 110.574
    return float(Polygon([(x * kx, y * ky) for x, y in g.exterior.coords]).area)


def cells_for_polygon(geojson: dict, res: int) -> list[str]:
    cells = h3.geo_to_cells(geojson, res)
    return sorted(cells)


def cell_polygon(cell: str) -> dict:
    ring = [[lng, lat] for lat, lng in h3.cell_to_boundary(cell)]
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def cell_center(cell: str) -> tuple[float, float]:
    return h3.cell_to_latlng(cell)


def cell_area_km2(cell: str) -> float:
    return h3.cell_area(cell, unit="km^2")


def pixel_cell_labels(t: GridTransform, cells: list[str], res: int) -> np.ndarray:
    """Map every raster pixel to the index of its H3 cell in `cells` (-1 if outside)."""
    lon, lat = t.pixel_centers()
    index = {c: i for i, c in enumerate(cells)}
    lab = np.full(lon.shape, -1, dtype=np.int32)
    cache: dict[str, int] = {}
    flat_lat, flat_lon = lat.ravel(), lon.ravel()
    out = lab.ravel()
    for k in range(out.size):
        c = h3.latlng_to_cell(float(flat_lat[k]), float(flat_lon[k]), res)
        i = cache.get(c)
        if i is None:
            i = index.get(c, -1)
            cache[c] = i
        out[k] = i
    return out.reshape(lab.shape)


def zonal_mean(labels: np.ndarray, values: np.ndarray, n: int, weights: np.ndarray | None = None) -> np.ndarray:
    ok = (labels >= 0) & np.isfinite(values)
    w = np.ones_like(values, dtype=float) if weights is None else weights
    num = np.bincount(labels[ok], weights=(values * w)[ok], minlength=n)
    den = np.bincount(labels[ok], weights=w[ok], minlength=n)
    return np.divide(num, den, out=np.zeros(n), where=den > 0)


def zonal_sum(labels: np.ndarray, values: np.ndarray, n: int) -> np.ndarray:
    ok = (labels >= 0) & np.isfinite(values)
    return np.bincount(labels[ok], weights=values[ok], minlength=n)


def polygon_from_mask(t: GridTransform, mask: np.ndarray, simplify_px: float = 1.5) -> dict | None:
    """Vectorise a boolean mask into a (multi)polygon footprint (for DB / export)."""
    try:
        import rasterio.features
        from rasterio.transform import from_bounds
    except Exception:  # rasterio optional
        return None
    if not mask.any():
        return None
    transform = from_bounds(t.west, t.south, t.east, t.north, t.width, t.height)
    polys = [shape(g) for g, v in rasterio.features.shapes(mask.astype("uint8"), mask=mask, transform=transform) if v == 1]
    from shapely.ops import unary_union

    u = unary_union(polys)
    tol = simplify_px * (t.east - t.west) / t.width
    return mapping(u.simplify(tol))


def geojson_bbox_polygon(w, s, e, n) -> dict:
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}
