"""Exports: GeoJSON, KML, CSV, COG (+ raster layer PNGs). All carry event/timestamp/source/model/confidence metadata."""
from __future__ import annotations

import csv
import io
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DataSource, Event, H3Cell, HazardDetection, RoadSegment
from .common import now
from .pipeline import event_dir

KML_COLORS = {"P1": "ff2b2bd9", "P2": "ff1f7be8", "P3": "ff1ccdf2", "P4": "ff8a8a8a"}  # aabbggrr
HAZ_PALETTE = {"flood": [(190, 230, 255), (30, 110, 220), (10, 30, 120)], "wildfire": [(255, 220, 120), (255, 120, 20), (120, 10, 10)],
               "landslide": [(240, 210, 160), (190, 120, 60), (90, 40, 20)], "cyclone": [(210, 200, 255), (130, 80, 220), (60, 20, 120)]}


def metadata(db: Session, event: Event) -> dict:
    det = db.scalars(select(HazardDetection).where(HazardDetection.event_id == event.id).order_by(HazardDetection.id.desc())).first()
    return {"event": event.code, "event_name": event.name, "hazard": event.hazard, "generated_at": now().isoformat(), "assessment_version": event.assessment_version,
            "data_sources": [f"{d.name} [{'SIMULATED' if d.is_simulated else d.provider}]" for d in db.scalars(select(DataSource).where(DataSource.event_id == event.id))],
            "model": f"{det.model_name} v{det.model_version}" if det else None, "sensor_mode": det.sensor_mode if det else None,
            "mean_detection_confidence": det.mean_confidence if det else None,
            "disclaimer": "DEMO / SIMULATED DATA. Not live satellite imagery. AI outputs are decision support, not authority." if event.is_demo else ""}


def cell_props(c: H3Cell) -> dict:
    return {"h3_index": c.h3_index, "cell_no": c.cell_no, "priority_level": c.priority_level, "priority_score": c.priority_score, "confidence": c.confidence,
            "confidence_label": c.confidence_label, "severity": round(c.severity, 3), "hazard_fraction": round(c.hazard_fraction, 3), "affected_area_km2": round(c.affected_area_km2, 3),
            "population": c.population, "population_exposed": c.population_exposed, "population_high_risk": c.population_high_risk, "population_isolated": c.population_isolated,
            "vulnerable_population": c.vulnerable_population, "vulnerability_score": c.vulnerability_score, "critical_facility_count": c.critical_facility_count,
            "infrastructure_score": c.infrastructure_score, "access_loss": c.access_loss, "road_status": c.road_status, "cascade_risk": c.cascade_risk, "field_status": c.field_status,
            "reason_codes": [r["label"] for r in c.reason_codes], "recommended_action": c.recommended_action}


def geojson(db: Session, event: Event) -> dict:
    cells = db.scalars(select(H3Cell).where(H3Cell.event_id == event.id).order_by(H3Cell.cell_no)).all()
    return {"type": "FeatureCollection", "metadata": metadata(db, event),
            "features": [{"type": "Feature", "id": c.h3_index, "geometry": c.geom, "properties": cell_props(c)} for c in cells]}


def csv_text(db: Session, event: Event) -> str:
    cells = db.scalars(select(H3Cell).where(H3Cell.event_id == event.id).order_by(H3Cell.cell_no)).all()
    meta = metadata(db, event)
    buf = io.StringIO()
    for k in ("event", "generated_at", "model", "sensor_mode", "disclaimer"):
        buf.write(f"# {k}: {meta[k]}\n")
    rows = [cell_props(c) | {"lat": round(c.lat, 6), "lon": round(c.lon, 6)} for c in cells]
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()) if rows else ["empty"])
    w.writeheader()
    for r in rows:
        r["reason_codes"] = "; ".join(r["reason_codes"])
        w.writerow(r)
    return buf.getvalue()


def kml_text(db: Session, event: Event) -> str:
    cells = db.scalars(select(H3Cell).where(H3Cell.event_id == event.id).order_by(H3Cell.cell_no)).all()
    meta = metadata(db, event)
    styles = "".join(f'<Style id="{k}"><LineStyle><color>ff000000</color><width>1</width></LineStyle><PolyStyle><color>99{v[2:]}</color></PolyStyle></Style>' for k, v in KML_COLORS.items())
    marks = []
    for c in cells:
        if c.priority_level == "P4" and c.severity < 0.03:
            continue
        ring = " ".join(f"{x},{y},0" for x, y in c.geom["coordinates"][0])
        desc = (f"<![CDATA[Priority {c.priority_level} ({c.priority_score:.2f}), confidence {c.confidence:.0%}<br/>Exposed {c.population_exposed:,}<br/>"
                f"Reasons: {escape('; '.join(r['label'] for r in c.reason_codes[:4]))}<br/>Action: {escape(c.recommended_action)}]]>")
        marks.append(f"<Placemark><name>Cell {c.cell_no:02d} {c.priority_level}</name><styleUrl>#{c.priority_level}</styleUrl><description>{desc}</description>"
                     f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{ring}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>")
    head = escape(f"{meta['event']} | {meta['generated_at']} | model {meta['model']} | {meta['disclaimer']}")
    return (f'<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>DISHA {escape(event.code)}</name>'
            f"<description>{head}</description>{styles}{''.join(marks)}</Document></kml>")


def cog_bytes(event: Event, layer: str = "severity") -> bytes:
    import rasterio
    from rasterio.transform import from_bounds
    path = event_dir(event.id) / "rasters.npz"
    if not path.exists():
        raise FileNotFoundError("No rasters for this event; run analysis first.")
    z = np.load(path)
    arr = z[layer].astype("float32") if layer in z else z["severity"].astype("float32")
    h, w = arr.shape
    west, south, east, north = z["bounds"]
    tmp = event_dir(event.id) / f"{layer}.cog.tif"
    profile = dict(driver="COG", height=h, width=w, count=1, dtype="float32", crs="EPSG:4326", transform=from_bounds(west, south, east, north, w, h), compress="deflate")
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(np.nan_to_num(arr), 1)
        dst.update_tags(event=event.code, layer=layer, generated=now().isoformat(), note="DEMO / SIMULATED DATA" if event.is_demo else "")
    return tmp.read_bytes()


def _ramp(v: np.ndarray, pal):
    v = np.clip(v, 0, 1)
    out = np.zeros(v.shape + (3,), np.float32)
    lo = v < 0.5
    t = np.where(lo, v / 0.5, (v - 0.5) / 0.5)[..., None]
    a = np.where(lo[..., None], np.array(pal[0]), np.array(pal[1]))
    b = np.where(lo[..., None], np.array(pal[1]), np.array(pal[2]))
    return (a + (b - a) * t).astype(np.uint8)


def layer_png(event: Event, layer: str) -> tuple[bytes, list[float]]:
    path = event_dir(event.id) / "rasters.npz"
    if not path.exists():
        raise FileNotFoundError("No rasters for this event")
    z = np.load(path)
    west, south, east, north = [float(x) for x in z["bounds"]]
    if layer in ("sar_pre", "sar_post"):
        a = z["pre_sar" if layer == "sar_pre" else "post_sar"]
        g = np.clip((a + 25) / 25, 0, 1)
        rgba = np.dstack([g * 255, g * 255, g * 255, np.full(g.shape, 255)]).astype(np.uint8)
    elif layer in ("hazard", "severity"):
        sev, mask = z["severity"], z["mask"]
        rgb = _ramp(0.25 + 0.75 * sev, HAZ_PALETTE.get(event.hazard, HAZ_PALETTE["flood"]))
        rgba = np.dstack([rgb, np.where(mask, 170, 0).astype(np.uint8)])
    elif layer == "confidence":
        c, mask = z["confidence"], z["mask"]
        rgb = _ramp(c, [(200, 60, 60), (240, 200, 60), (60, 190, 120)])
        rgba = np.dstack([rgb, np.where(mask, 190, 0).astype(np.uint8)])
    elif layer == "population":
        p = z["pop"]
        v = np.clip(np.log1p(p) / max(np.log1p(p.max()), 1e-6), 0, 1)
        rgb = _ramp(v, [(40, 30, 80), (200, 80, 160), (255, 230, 120)])
        rgba = np.dstack([rgb, np.where(p > 0.01, 150, 0).astype(np.uint8)])
    elif layer == "optical":
        if "rgb" not in z:
            raise KeyError(layer)
        rgb = z["rgb"]
        rgba = np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])
    elif layer == "optical_ndvi":
        v = np.nan_to_num(z["post_ndvi"], nan=0.0)
        cl = z["cloud"]
        rgb = _ramp((v + 0.2) / 1.0, [(120, 90, 60), (200, 200, 90), (30, 140, 50)])
        rgba = np.dstack([rgb, np.where(cl, 0, 200).astype(np.uint8)])
    else:
        raise KeyError(layer)
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG", optimize=True)
    return buf.getvalue(), [west, south, east, north]


def road_geojson(db: Session, event_id: int) -> dict:
    segs = db.scalars(select(RoadSegment).where(RoadSegment.event_id == event_id)).all()
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": s.geom, "properties": {
        "name": s.name, "class": s.road_class, "status": s.status, "is_bridge": s.is_bridge, "critical": s.is_critical, "length_m": round(s.length_m)}} for s in segs]}
