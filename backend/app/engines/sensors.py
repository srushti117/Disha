"""Sensor switching engine: chooses SAR/optical strategy and explains why."""
from dataclasses import asdict, dataclass

CLOUD_LIMIT_PCT = 30.0


@dataclass
class SensorDecision:
    mode: str  # SAR+OPTICAL | SAR-FIRST | SAR-ONLY | OPTICAL-ONLY | NO-DATA
    primary: str
    optical_weight: float  # 0..1 influence of optical evidence on confidence
    cloud_cover_pct: float | None
    explanation: str

    def to_dict(self):
        return asdict(self)


def decide_sensors(
    cloud_cover_pct: float | None,
    optical_available: bool,
    sar_available: bool = True,
    hazard: str = "flood",
    thermal_available: bool = False,
) -> SensorDecision:
    """Spec §18. Wildfire/landslide lean on optical indices; the engine says so when it must degrade."""
    optical_primary = hazard in ("wildfire", "landslide")
    if not sar_available and not optical_available:
        return SensorDecision("NO-DATA", "none", 0.0, cloud_cover_pct, "No usable satellite data. Detection cannot run.")
    if not sar_available:
        return SensorDecision(
            "OPTICAL-ONLY", "Sentinel-2", 1.0, cloud_cover_pct,
            "Sentinel-1 SAR unavailable. Optical imagery is the only source; cloud-masked pixels have no evidence.",
        )
    if not optical_available or cloud_cover_pct is None:
        extra = " VIIRS thermal hotspots supplement detection." if (hazard == "wildfire" and thermal_available) else ""
        return SensorDecision(
            "SAR-ONLY", "Sentinel-1 SAR", 0.0, cloud_cover_pct,
            "Optical imagery unavailable. Sentinel-1 SAR is the sole detection source." + extra,
        )
    if cloud_cover_pct < CLOUD_LIMIT_PCT:
        lead = "Sentinel-2 optical" if optical_primary else "Sentinel-1 SAR"
        return SensorDecision(
            "SAR+OPTICAL", lead, 0.5 if not optical_primary else 0.65, cloud_cover_pct,
            f"Cloud cover {cloud_cover_pct:.0f}% is below {CLOUD_LIMIT_PCT:.0f}%. SAR and optical are fused; {lead} leads for {hazard}.",
        )
    w = round(max(0.05, 0.4 * (1 - cloud_cover_pct / 100)), 2)
    extra = " VIIRS thermal hotspots remain usable under cloud." if (hazard == "wildfire" and thermal_available) else ""
    return SensorDecision(
        "SAR-FIRST", "Sentinel-1 SAR", w, cloud_cover_pct,
        f"Optical imagery downgraded due to high cloud cover ({cloud_cover_pct:.0f}%). Sentinel-1 SAR selected as primary source; "
        f"optical used only on cloud-free pixels (weight {w}).{extra}",
    )
