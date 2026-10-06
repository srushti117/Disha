"""Rainfall / wind from Open-Meteo (ERA5 reanalysis for past events, forecast for ongoing ones). No API key."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .net import LiveDataError, http_json


def rainfall_after(lat: float, lon: float, t0: datetime) -> dict:
    """Cumulative rainfall 6/12/24 h after `t0`. For a past event this is observed/reanalysed rain used as a stand-in for a forecast
    ('historical replay'); for a current event it is the model forecast. The `note` says which."""
    now = datetime.now(timezone.utc)
    end = t0 + timedelta(hours=24)
    past = t0 < now - timedelta(days=6)
    base = "https://archive-api.open-meteo.com/v1/archive" if past else "https://api.open-meteo.com/v1/forecast"
    params = {"latitude": lat, "longitude": lon, "hourly": "precipitation,wind_speed_10m", "timezone": "UTC", "wind_speed_unit": "kmh"}
    d0, d1 = t0.date(), end.date()
    if past:
        params.update(start_date=str(d0), end_date=str(d1))
    else:
        params.update(past_days=1, forecast_days=3)
    try:
        j = http_json("GET", base, params=params)
        times = [datetime.fromisoformat(x).replace(tzinfo=timezone.utc) for x in j["hourly"]["time"]]
        pr, wd = j["hourly"]["precipitation"], j["hourly"]["wind_speed_10m"]
    except (LiveDataError, KeyError, ValueError) as e:
        raise LiveDataError(f"Open-Meteo unavailable: {e}")
    out = {}
    for h in (6, 12, 24):
        lim = t0 + timedelta(hours=h)
        out[str(h)] = round(sum(p or 0 for tt, p in zip(times, pr) if t0 <= tt < lim), 1)
    win = [w or 0 for tt, w in zip(times, wd) if t0 <= tt < end]
    return {"rainfall_mm": out, "river_level_trend_m_per_h": 0.0, "wind_kmh": round(max(win), 1) if win else 0.0,
            "source": "Open-Meteo " + ("ERA5 reanalysis" if past else "forecast"),
            "note": ("Historical replay: observed rainfall in the 24 h after the satellite pass is used in place of a forecast. River level is not available (0)."
                     if past else "Model forecast. River level is not available (0).")}
