"""Demonstration scenarios. ALL data generated from these specs is DEMO / SIMULATED (see demo/world.py)."""
import math
from datetime import datetime, timezone

DEMO_LABEL = "DEMONSTRATION DATA"


def bbox(lat: float, lon: float, w_km: float, h_km: float) -> tuple[float, float, float, float]:
    dlat = h_km / 110.574 / 2
    dlon = w_km / (111.32 * math.cos(math.radians(lat))) / 2
    return (round(lon - dlon, 5), round(lat - dlat, 5), round(lon + dlon, 5), round(lat + dlat, 5))


def _d(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


SCENARIOS: dict[str, dict] = {
    "kerala_flood_2018": {
        "title": "Kerala Floods 2018", "hazard": "flood", "variant": "flood_river", "seed": 11, "severity": "extreme",
        "name": "Kerala Flood Demo (2018 scenario)", "center": (10.30, 76.33), "extent_km": (12, 12),
        "description": "Monsoon river flood over a Periyar-basin-like floodplain. Rasters, population, roads and facilities are simulated.",
        "event_start": _d(2018, 8, 15), "pre_date": _d(2018, 8, 4, 0, 46), "post_date": _d(2018, 8, 22, 0, 46),
        "params": {"cloud_pct": 78, "pop_total": 96_000, "n_villages": 15, "flood_level_m": 4.3,
                   "weather": {"rainfall_mm": {"6": 38, "12": 66, "24": 112}, "river_level_trend_m_per_h": 0.11, "wind_kmh": 24,
                               "source": "DEMO / SIMULATED forecast", "note": "Not a live weather feed."}},
    },
    "wayanad_landslide_2024": {
        "title": "Wayanad Landslide 2024", "hazard": "landslide", "variant": "landslide", "seed": 5, "severity": "extreme",
        "name": "Wayanad Landslide Demo (2024 scenario)", "center": (11.50, 76.18), "extent_km": (9, 9),
        "description": "Steep-slope failure above a valley settlement with debris run-out. Terrain and imagery are simulated.",
        "event_start": _d(2024, 7, 30), "pre_date": _d(2024, 7, 18, 0, 46), "post_date": _d(2024, 8, 1, 0, 46),
        "params": {"cloud_pct": 86, "pop_total": 18_000, "n_villages": 8, "relief_m": 1500,
                   "resources": {"rescue_team": 10, "ambulance": 5, "boat": 0, "medical_team": 4, "drone": 4, "relief_vehicle": 5},
                   "weather": {"rainfall_mm": {"6": 45, "12": 80, "24": 140}, "river_level_trend_m_per_h": 0.0, "wind_kmh": 15,
                               "source": "DEMO / SIMULATED forecast", "note": "Not a live weather feed."}},
    },
    "urban_flood_synthetic": {
        "title": "Synthetic Urban Flood", "hazard": "flood", "variant": "flood_urban", "seed": 23, "severity": "high",
        "name": "Synthetic Urban Flood Demo", "center": (19.10, 72.88), "extent_km": (8, 8),
        "description": "Fictional dense city with pluvial flooding. Flooded built-up areas brighten SAR, so detection is deliberately harder.",
        "event_start": _d(2025, 7, 8), "pre_date": _d(2025, 6, 28, 0, 46), "post_date": _d(2025, 7, 9, 0, 46),
        "params": {"cloud_pct": 92, "pop_total": 160_000, "n_villages": 20, "pluvial_pct": 27,
                   "weather": {"rainfall_mm": {"6": 55, "12": 90, "24": 150}, "river_level_trend_m_per_h": 0.05, "wind_kmh": 30,
                               "source": "DEMO / SIMULATED forecast", "note": "Not a live weather feed."}},
    },
    "wildfire_demo": {
        "title": "Forest Wildfire", "hazard": "wildfire", "variant": "wildfire", "seed": 31, "severity": "high",
        "name": "Wildfire Demo (Himalayan foothill scenario)", "center": (29.38, 79.45), "extent_km": (12, 12),
        "description": "Wind-driven forest fire with burn scar and VIIRS-style thermal hotspots. Burn severity and hotspots are simulated.",
        "event_start": _d(2025, 4, 28), "pre_date": _d(2025, 4, 16, 0, 46), "post_date": _d(2025, 4, 30, 0, 46),
        "params": {"cloud_pct": 22, "pop_total": 9_000, "n_villages": 6, "wind_deg": 35, "relief_m": 420,
                   "resources": {"rescue_team": 10, "ambulance": 4, "boat": 0, "medical_team": 3, "drone": 4, "relief_vehicle": 5},
                   "weather": {"rainfall_mm": {"6": 0, "12": 0, "24": 2}, "river_level_trend_m_per_h": 0.0, "wind_kmh": 38,
                               "source": "DEMO / SIMULATED forecast", "note": "Not a live weather feed."}},
    },
    "cyclone_demo": {
        "title": "Coastal Cyclone", "hazard": "cyclone", "variant": "cyclone", "seed": 41, "severity": "extreme",
        "name": "Cyclone Demo (Odisha-coast-like scenario)", "center": (19.80, 85.82), "extent_km": (12, 12),
        "description": "Coastal landfall with vegetation damage, roof damage proxy and storm-surge indicator. All imagery simulated.",
        "event_start": _d(2019, 5, 3), "pre_date": _d(2019, 4, 24, 0, 46), "post_date": _d(2019, 5, 5, 0, 46),
        "params": {"cloud_pct": 95, "pop_total": 70_000, "n_villages": 14, "surge_km": 3.6,
                   "weather": {"rainfall_mm": {"6": 60, "12": 95, "24": 130}, "river_level_trend_m_per_h": 0.08, "wind_kmh": 90,
                               "source": "DEMO / SIMULATED forecast", "note": "Not a live weather feed."}},
    },
}


# REAL events: retrieved from open data at analysis time (Sentinel-1/2, Copernicus DEM, ESA WorldCover, WorldPop, OpenStreetMap, Open-Meteo).
LIVE_SCENARIOS: dict[str, dict] = {
    "kerala_kuttanad_2018": {
        "title": "Kerala floods 2018 - Kuttanad (real data)", "hazard": "flood", "severity": "extreme", "name": "Kerala floods 2018 - Kuttanad", "center": (9.465, 76.425), "extent_km": (12, 12),
        "description": "Real Sentinel-1 before/after the August 2018 floods over the Kuttanad backwaters (Alappuzha), real OpenStreetMap roads and facilities, WorldPop population.",
        "event_start": _d(2018, 8, 15), "pre_end": "2018-08-12", "post_start": "2018-08-17", "post_end": "2018-09-10", "params": {"iso3": "IND"},
    },
    "kerala_chalakudy_2018": {
        "title": "Kerala floods 2018 - Chalakudy (real data)", "hazard": "flood", "severity": "high", "name": "Kerala floods 2018 - Chalakudy", "center": (10.30, 76.33), "extent_km": (12, 12),
        "description": "Real Sentinel-1 over the Chalakudy river basin. The first usable post-flood radar pass is 21 Aug 2018, when much of the water had already receded, so the detected area is small.",
        "event_start": _d(2018, 8, 15), "pre_end": "2018-08-12", "post_start": "2018-08-17", "post_end": "2018-08-26", "params": {"iso3": "IND"},
    },
    "sindh_floods_2022": {
        "title": "Pakistan floods 2022 - Sindh (real data)", "hazard": "flood", "severity": "extreme", "name": "Pakistan floods 2022 - Sindh", "center": (26.62, 67.75), "extent_km": (14, 14),
        "description": "Real Sentinel-1 before/after the 2022 monsoon floods near Dadu, Sindh, with real OpenStreetMap roads and WorldPop population. Very large, persistent inundation.",
        "event_start": _d(2022, 8, 25), "pre_end": "2022-07-25", "post_start": "2022-08-30", "post_end": "2022-09-20", "params": {"iso3": "PAK"},
    },
}


def scenario_bounds(key: str):
    s = SCENARIOS.get(key) or LIVE_SCENARIOS[key]
    return bbox(*s["center"], *s["extent_km"])


def list_scenarios() -> list[dict]:
    sim = [{"key": k, "title": v["title"], "hazard": v["hazard"], "description": v["description"], "label": DEMO_LABEL, "mode": "simulated",
            "center": v["center"], "bounds": scenario_bounds(k), "event_start": v["event_start"].isoformat()} for k, v in SCENARIOS.items()]
    live = [{"key": k, "title": v["title"], "hazard": v["hazard"], "description": v["description"], "label": "REAL DATA", "mode": "live",
             "center": v["center"], "bounds": scenario_bounds(k), "event_start": v["event_start"].isoformat(),
             "pre_end": v["pre_end"], "post_start": v["post_start"], "post_end": v["post_end"]} for k, v in LIVE_SCENARIOS.items()]
    return live + sim


# Administrative-area picker (Method 3). Bounding boxes are coarse placeholders for the demo picker, not official boundaries.
ADMIN_AREAS = [
    {"id": "ernakulam", "name": "Ernakulam district, Kerala (approx. box)", "bounds": (76.17, 9.65, 76.65, 10.18)},
    {"id": "thrissur", "name": "Thrissur district, Kerala (approx. box)", "bounds": (76.02, 10.18, 76.55, 10.75)},
    {"id": "wayanad", "name": "Wayanad district, Kerala (approx. box)", "bounds": (75.8, 11.5, 76.45, 11.95)},
    {"id": "puri", "name": "Puri district, Odisha (approx. box)", "bounds": (85.4, 19.6, 86.1, 20.2)},
]
