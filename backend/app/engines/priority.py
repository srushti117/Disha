"""Explainable Impact Priority Index (PI).

PI = wS*S + wE*E + wC*C + wA*A   (defaults 0.35 / 0.30 / 0.20 / 0.15, all inputs normalised to 0..1)
  S  change severity x model confidence
  E  population exposure (0.75*normalised exposed pop + 0.25*vulnerability score scaled by people present)
  C  critical-infrastructure hit
  A  access loss (roads cut / community isolated)
Every result carries component values, weighted contributions, reason codes and a recommended action.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

DEFAULT_WEIGHTS = {"severity": 0.35, "exposure": 0.30, "infrastructure": 0.20, "accessibility": 0.15}
DEFAULT_THRESHOLDS = {"P1": 0.48, "P2": 0.34, "P3": 0.20}  # PI >= threshold -> level; else P4
LEVEL_NAMES = {"P1": "CRITICAL", "P2": "HIGH", "P3": "MODERATE", "P4": "LOW"}
LEVEL_RANK = {"P1": 1, "P2": 2, "P3": 3, "P4": 4, "RESOLVED": 5}
EXPOSURE_REF_FLOOR = 300.0  # normalisation reference never below this many people
MIN_SEVERITY_FOR_RESPONSE = 0.03  # below this the cell is treated as unaffected

CONFIDENCE_BANDS = [(0.80, "HIGH CONFIDENCE"), (0.60, "MEDIUM CONFIDENCE"), (0.40, "LOW CONFIDENCE")]


def confidence_label(c: float | None) -> str:
    if c is None:
        return "INSUFFICIENT DATA"
    for lo, name in CONFIDENCE_BANDS:
        if c >= lo:
            return name
    return "INSUFFICIENT DATA"


def normalise_weights(w: dict | None) -> dict:
    w = {**DEFAULT_WEIGHTS, **(w or {})}
    s = sum(max(0.0, v) for v in w.values()) or 1.0
    return {k: max(0.0, v) / s for k, v in w.items()}


@dataclass
class PriorityInput:
    severity: float
    confidence: float
    exposure_pop_norm: float  # exposed population normalised 0..1 vs event reference
    vulnerability: float
    infrastructure_score: float
    access_loss: float
    # facts used for reason codes
    population_exposed: int = 0
    vulnerable_population: int = 0
    hospitals: int = 0
    schools: int = 0
    power: int = 0
    critical_facility_count: int = 0
    road_status: str = "unknown"
    isolated_population: int = 0
    cascade_risk: float = 0.0
    field_status: str = "unverified"
    hazard: str = "flood"


@dataclass
class PriorityOutput:
    score: float
    level: str
    components: dict
    contributions: dict
    confidence: float
    confidence_label: str
    reason_codes: list[dict] = field(default_factory=list)
    top_factors: list[str] = field(default_factory=list)
    recommended_action: str = ""

    def to_dict(self):
        return asdict(self)


HAZARD_NOUN = {"flood": "flood", "wildfire": "fire", "landslide": "landslide", "cyclone": "cyclone damage"}


def level_for(score: float, thresholds: dict | None = None) -> str:
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    if score >= t["P1"]:
        return "P1"
    if score >= t["P2"]:
        return "P2"
    if score >= t["P3"]:
        return "P3"
    return "P4"


def level_threshold(thresholds, key):
    return {**DEFAULT_THRESHOLDS, **(thresholds or {})}[key]


def compute_priority(inp: PriorityInput, weights: dict | None = None, thresholds: dict | None = None) -> PriorityOutput:
    w = normalise_weights(weights)
    clamp = lambda x: max(0.0, min(1.0, float(x)))  # noqa: E731
    S = clamp(inp.severity) * clamp(inp.confidence)
    E = clamp(0.75 * clamp(inp.exposure_pop_norm) + 0.25 * clamp(inp.vulnerability) * min(1.0, inp.population_exposed / 200.0))
    C = clamp(inp.infrastructure_score)
    A = clamp(inp.access_loss)
    comps = {"severity": S, "exposure": E, "infrastructure": C, "accessibility": A}
    contrib = {k: w[k] * v for k, v in comps.items()}
    score = sum(contrib.values())
    affected = inp.severity >= MIN_SEVERITY_FOR_RESPONSE
    level = level_for(score, thresholds) if affected else "P4"
    hazard_only = affected and inp.population_exposed < 10 and inp.isolated_population < 10 and inp.infrastructure_score <= 0.0
    if hazard_only and level in ("P1", "P2"):
        level = "P3"  # no people or critical assets exposed: ground assessment / containment, not rescue
        score = min(score, level_threshold(thresholds, "P2") - 0.001)
    if inp.field_status == "resolved":
        level, score = "P4", min(score, 0.05)
    reasons = reason_codes(inp, comps, contrib, level)
    return PriorityOutput(
        score=round(score, 4), level=level, components={k: round(v, 4) for k, v in comps.items()},
        contributions={k: round(v, 4) for k, v in contrib.items()}, confidence=round(clamp(inp.confidence), 4),
        confidence_label=confidence_label(inp.confidence), reason_codes=reasons,
        top_factors=[r["label"] for r in reasons[:4]], recommended_action=recommend_action(inp, level),
    )


def reason_codes(inp: PriorityInput, comps: dict, contrib: dict, level: str) -> list[dict]:
    noun = HAZARD_NOUN.get(inp.hazard, inp.hazard)
    cand: list[tuple[float, str, str]] = []  # (rank weight, code, label)
    if inp.severity >= 0.6:
        cand.append((contrib["severity"] + 0.20, "HIGH_SEVERITY", f"High {noun} severity ({inp.severity:.0%})"))
    elif inp.severity >= 0.35:
        cand.append((contrib["severity"] + 0.05, "MODERATE_SEVERITY", f"Moderate {noun} severity ({inp.severity:.0%})"))
    if inp.access_loss >= 0.5 or inp.road_status == "blocked":
        cand.append((contrib["accessibility"] + 0.12, "ROAD_ACCESS_DISRUPTED", "Road access disrupted"))
    elif inp.access_loss >= 0.2:
        cand.append((contrib["accessibility"], "ROAD_ACCESS_DEGRADED", "Road access partly degraded"))
    if inp.isolated_population > 0:
        cand.append((0.16, "COMMUNITY_ISOLATED", f"{inp.isolated_population:,} people potentially isolated"))
    if inp.hospitals:
        cand.append((contrib["infrastructure"] + 0.10, "HOSPITAL_NEARBY", "Hospital in or adjacent to affected area"))
    if inp.power:
        cand.append((contrib["infrastructure"] + 0.02, "POWER_AT_RISK", "Power substation in affected area"))
    if inp.schools:
        cand.append((contrib["infrastructure"] * 0.6, "SCHOOL_IN_ZONE", "School in affected zone"))
    if inp.cascade_risk >= 0.4:
        cand.append((0.08 + inp.cascade_risk * 0.1, "CASCADE_RISK", "Cascading dependency risk"))
    if comps["exposure"] >= 0.5 or inp.exposure_pop_norm >= 0.5:
        cand.append((contrib["exposure"] + 0.12, "HIGH_POPULATION_EXPOSURE", f"High population exposure ({inp.population_exposed:,} people)"))
    elif inp.population_exposed > 0:
        cand.append((contrib["exposure"], "POPULATION_EXPOSED", f"{inp.population_exposed:,} people exposed"))
    if inp.vulnerable_population >= 150:
        cand.append((0.07, "VULNERABLE_POPULATION", f"{inp.vulnerable_population:,} vulnerable people (children/elderly, estimated)"))
    if inp.field_status == "confirmed" or inp.field_status == "severe":
        cand.append((0.18, "FIELD_CONFIRMED", "Confirmed by field responder"))
    if inp.confidence < 0.6:
        cand.append((0.02, "LOW_CONFIDENCE", "Low detection confidence - verify on the ground"))
    if inp.severity >= MIN_SEVERITY_FOR_RESPONSE and inp.population_exposed < 10 and inp.isolated_population < 10 and inp.infrastructure_score <= 0.0:
        cand.append((0.5, "NO_EXPOSED_POPULATION", "No exposed population or critical assets (hazard-only area)"))
    cand.sort(key=lambda x: -x[0])
    return [{"code": c, "label": l} for _, c, l in cand]


def recommend_action(inp: PriorityInput, level: str) -> str:
    if inp.field_status == "resolved":
        return "Resolved by field team - continue monitoring."
    flooded = inp.hazard in ("flood", "cyclone")
    if level == "P1":
        bits = ["Dispatch search & rescue"]
        if flooded and (inp.road_status in ("blocked", "potentially_blocked") or inp.access_loss >= 0.5):
            bits.append("with boat support (road access impaired)")
        if inp.hospitals:
            bits.append("and verify hospital continuity")
        if inp.vulnerable_population >= 150:
            bits.append("- prioritise vulnerable residents")
        return " ".join(bits) + "."
    if level == "P2":
        return "Stage relief and plan evacuation within 6-12 h; confirm access route." if inp.access_loss < 0.5 else "Establish alternate route, then relief & evacuation within 6-12 h."
    if level == "P3":
        return "Schedule ground assessment and supply delivery."
    return "Monitor on next satellite pass."
