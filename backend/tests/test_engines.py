"""Unit tests for pure engines: priority, detection primitives, sensors, routing, evacuation, resources, escalation, cascade."""
import networkx as nx
import numpy as np
import pytest

from app.engines import escalation
from app.engines.change_detection import ChangeDetectionEngine, DetectionInputs, otsu_threshold, remove_small, speckle_filter
from app.engines.evaluation import compute_metrics
from app.engines.evacuation import plan_evacuation
from app.engines.fusion import overall_confidence, source_status
from app.engines.geo import GridTransform, cells_for_polygon, geojson_bbox_polygon, pixel_cell_labels, zonal_sum
from app.engines.priority import PriorityInput, compute_priority, confidence_label, level_for, normalise_weights
from app.engines.resources import allocate, scale_roster
from app.engines.routing import build_graph, route_options
from app.engines.sensors import decide_sensors
from app.engines.vulnerability import VulnInput, vulnerability_score


# ---------------------------------------------------------------- priority
def pin(**kw):
    base = dict(severity=0.9, confidence=1.0, exposure_pop_norm=0.9, vulnerability=0.5, infrastructure_score=0.9, access_loss=0.9, population_exposed=2000)
    base.update(kw)
    return PriorityInput(**base)


def test_priority_formula_matches_original_disha_index():
    out = compute_priority(pin(vulnerability=0.0, severity=1.0, confidence=1.0, exposure_pop_norm=1.0, infrastructure_score=1.0, access_loss=1.0))
    assert out.components["exposure"] == pytest.approx(0.75)  # E = 0.75*pop + 0.25*vuln
    expected = 0.35 * 1 + 0.30 * 0.75 + 0.20 * 1 + 0.15 * 1
    assert out.score == pytest.approx(expected, abs=1e-3)
    assert sum(out.contributions.values()) == pytest.approx(out.score, abs=1e-3)


def test_priority_levels_and_weights_configurable():
    assert level_for(0.9) == "P1" and level_for(0.4) == "P2" and level_for(0.25) == "P3" and level_for(0.05) == "P4"
    w = normalise_weights({"severity": 1, "exposure": 1, "infrastructure": 1, "accessibility": 1})
    assert sum(w.values()) == pytest.approx(1.0) and w["severity"] == pytest.approx(0.25)
    a = compute_priority(pin(severity=0.3, access_loss=0.0), {"severity": 1, "exposure": 0, "infrastructure": 0, "accessibility": 0})
    assert a.score == pytest.approx(0.3, abs=1e-3)


def test_priority_inputs_are_clamped_and_unaffected_is_p4():
    out = compute_priority(pin(severity=5, exposure_pop_norm=9, infrastructure_score=3, access_loss=2))
    assert 0 <= out.score <= 1 and all(0 <= v <= 1 for v in out.components.values())
    assert compute_priority(pin(severity=0.0)).level == "P4"


def test_reason_codes_never_empty_for_p1_and_explain():
    out = compute_priority(pin(hospitals=1, road_status="blocked"))
    assert out.level == "P1"
    codes = {r["code"] for r in out.reason_codes}
    assert {"HIGH_SEVERITY", "ROAD_ACCESS_DISRUPTED", "HOSPITAL_NEARBY"} <= codes
    assert "rescue" in out.recommended_action.lower()


def test_hazard_only_area_is_not_p1():
    out = compute_priority(pin(population_exposed=0, exposure_pop_norm=0, infrastructure_score=0, vulnerability=0))
    assert out.level in ("P3", "P4") and any(r["code"] == "NO_EXPOSED_POPULATION" for r in out.reason_codes)


def test_field_resolved_drops_priority():
    assert compute_priority(pin(field_status="resolved")).level == "P4"


def test_confidence_labels():
    assert confidence_label(0.91) == "HIGH CONFIDENCE" and confidence_label(0.65) == "MEDIUM CONFIDENCE"
    assert confidence_label(0.45) == "LOW CONFIDENCE" and confidence_label(0.1) == "INSUFFICIENT DATA" and confidence_label(None) == "INSUFFICIENT DATA"


# ---------------------------------------------------------------- detection primitives
def test_otsu_separates_bimodal():
    rng = np.random.default_rng(0)
    v = np.concatenate([rng.normal(-12, 1, 5000), rng.normal(-1, 1, 5000)])
    t, sep = otsu_threshold(v)
    assert -8 < t < -4 and sep > 0.8


def test_speckle_filter_reduces_variance():
    rng = np.random.default_rng(1)
    img = (10 * np.log10(rng.gamma(4, 0.25, (80, 80)) * 0.1)).astype(np.float32)
    assert speckle_filter(img).std() < img.std() * 0.6


def test_remove_small_blobs():
    m = np.zeros((20, 20), bool)
    m[2:4, 2:4] = True
    m[10:18, 10:18] = True
    out = remove_small(m, 10)
    assert not out[2, 2] and out[12, 12]


def _toy_flood_inputs(cloud=None):
    rng = np.random.default_rng(3)
    pre = rng.normal(-9, 0.5, (120, 120)).astype(np.float32)
    post = pre + rng.normal(0, 0.3, (120, 120)).astype(np.float32)
    truth = np.zeros((120, 120), bool)
    truth[30:90, 30:90] = True
    post[truth] = rng.normal(-20, 0.6, truth.sum())
    pre[:, :6] = -22  # permanent river
    post[:, :6] = -22
    slope = np.zeros((120, 120), np.float32)
    slope[:, 100:] = 20  # steep hill that is also dark after event
    post[:, 100:] = -19
    t = GridTransform(76.0, 10.0, 76.1, 10.1, 120, 120)
    inp = DetectionInputs("flood", pre, post, quality_mask=np.ones((120, 120), bool), slope_deg=slope, dem=np.zeros((120, 120), np.float32), transform=t)
    return inp, truth


def test_flood_detection_masks_permanent_water_and_steep_terrain():
    inp, truth = _toy_flood_inputs()
    r = ChangeDetectionEngine().detect(inp)
    assert (r.mask & truth).sum() / truth.sum() > 0.9
    assert not r.mask[:, :6].any(), "permanent water must be excluded"
    assert not r.mask[:, 100:].any(), "steep terrain must be masked"
    assert r.confidence[r.mask].mean() > 0.6 and r.model_name and r.model_version


def test_engine_falls_back_and_says_so():
    inp, _ = _toy_flood_inputs()
    r = ChangeDetectionEngine().detect(inp, prefer="siamese_unet")
    assert r.model_name == "disha-rule-based" and any("unavailable" in n for n in r.notes)


def test_random_forest_trainable(tmp_path, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "models_dir", tmp_path)
    from app.engines.change_detection import RandomForestDetector
    inp, truth = _toy_flood_inputs()
    rf = RandomForestDetector("flood")
    assert rf.is_available()[0] is False
    rf.fit(inp, truth, n_estimators=10)
    r = ChangeDetectionEngine().detect(inp, prefer="random_forest")
    assert r.model_name == "disha-random-forest"
    assert (r.mask & truth).sum() / truth.sum() > 0.8


def test_evaluation_metrics():
    p = np.array([1, 1, 0, 0], bool)
    t = np.array([1, 0, 1, 0], bool)
    m = compute_metrics(p, t)
    assert m["precision"] == 0.5 and m["recall"] == 0.5 and m["iou"] == pytest.approx(1 / 3, abs=1e-3)


# ---------------------------------------------------------------- sensors
def test_sensor_switching_matches_spec():
    assert decide_sensors(10, True).mode == "SAR+OPTICAL"
    d = decide_sensors(78, True)
    assert d.mode == "SAR-FIRST" and "Optical imagery downgraded due to high cloud cover" in d.explanation and "Sentinel-1 SAR selected as primary" in d.explanation
    assert decide_sensors(None, False).mode == "SAR-ONLY"
    assert decide_sensors(10, True, sar_available=False).mode == "OPTICAL-ONLY"
    assert decide_sensors(None, False, sar_available=False).mode == "NO-DATA"


# ---------------------------------------------------------------- geo
def test_h3_grid_and_zonal_aggregation():
    poly = geojson_bbox_polygon(76.30, 10.30, 76.34, 10.34)
    cells = cells_for_polygon(poly, 8)
    assert 5 < len(cells) < 40
    t = GridTransform(76.30, 10.30, 76.34, 10.34, 80, 80)
    labels = pixel_cell_labels(t, cells, 8)
    total = zonal_sum(labels, np.ones((80, 80)), len(cells))
    assert total.sum() > 0.7 * 80 * 80
    px = t.pixel_size_m
    assert 40 < px[0] < 60


def test_transform_roundtrip():
    t = GridTransform(76.0, 10.0, 76.2, 10.2, 100, 100)
    lon, lat = t.rc_to_lonlat(25, 50)
    r, c = t.lonlat_to_rc(lon, lat)
    assert (int(r), int(c)) == (25, 50)


# ---------------------------------------------------------------- routing
def _graph():
    nodes = {0: (10.0, 76.0), 1: (10.0, 76.01), 2: (10.0, 76.02), 3: (10.01, 76.01), 4: (10.02, 76.02)}
    def seg(u, v, st="open", L=1000, cls="secondary"):
        return {"id": None, "name": f"R{u}-{v}", "class": cls, "u": u, "v": v, "length_m": L, "is_bridge": False, "status": st, "h3_indices": [], "coords": []}
    segs = [seg(0, 1, "blocked", 1000), seg(1, 2, "open", 1000), seg(0, 3, "open", 1800), seg(3, 2, "open", 1800), seg(2, 4, "open", 1000)]
    return build_graph(segs), nodes


def test_routing_shortest_may_be_blocked_but_recommended_is_open():
    G, nodes = _graph()
    out = route_options(G, nodes, 0, 4)
    assert out["routes"]["shortest"].blocked_segments == 1 and not out["routes"]["shortest"].feasible
    assert out["routes"]["fastest"].blocked_segments == 0 and out["routes"]["safest"].blocked_segments == 0
    assert out["recommended"] in ("fastest", "safest")
    assert out["routes"]["fastest"].distance_km == pytest.approx(4.6)


def test_routing_no_open_route():
    G, nodes = _graph()
    for u, v in [(0, 3), (0, 1)]:
        G[u][v]["status"] = "blocked"
    out = route_options(G, nodes, 0, 4)
    assert out["recommended"] is None and not out["routes"]["fastest"].feasible


# ---------------------------------------------------------------- evacuation
def test_evacuation_respects_capacity_and_flags_shortage():
    G, nodes = _graph()
    cells = [{"h3_index": "a", "cell_no": 1, "priority_level": "P1", "priority_score": 0.9, "population_exposed": 700, "isolated": False},
             {"h3_index": "b", "cell_no": 2, "priority_level": "P2", "priority_score": 0.5, "population_exposed": 500, "isolated": False}]
    shelters = [{"id": 1, "name": "S1", "capacity": 600, "occupied": 100, "in_hazard_zone": False},
                {"id": 2, "name": "S2", "capacity": 400, "occupied": 0, "in_hazard_zone": False},
                {"id": 3, "name": "Unsafe", "capacity": 5000, "occupied": 0, "in_hazard_zone": True}]
    plan = plan_evacuation(cells, shelters, G, {"a": 0, "b": 3}, {1: 2, 2: 4, 3: 2})
    used = {}
    for a in plan["assignments"]:
        used[a["shelter_id"]] = used.get(a["shelter_id"], 0) + a["people"]
    assert used[1] <= 500 and used[2] <= 400 and 3 not in used
    assert plan["summary"]["shortfall"] == 1200 - 900
    types = {f["type"] for f in plan["flags"]}
    assert "insufficient_capacity" in types and "shelter_in_hazard_zone" in types


def test_evacuation_unreachable():
    G, nodes = _graph()
    for u, v in list(G.edges):
        G[u][v]["status"] = "blocked"
    cells = [{"h3_index": "a", "cell_no": 1, "priority_level": "P1", "priority_score": 0.9, "population_exposed": 100, "isolated": True}]
    plan = plan_evacuation(cells, [{"id": 1, "name": "S1", "capacity": 500, "occupied": 0, "in_hazard_zone": False}], G, {"a": 0}, {1: 4})
    assert plan["flags"][0]["type"] == "unreachable_shelter"


# ---------------------------------------------------------------- resources
def _cells():
    return [{"h3_index": f"c{i}", "cell_no": i, "priority_level": "P1", "priority_score": 0.9 - i * 0.05, "population_exposed": 2000, "vulnerable_population": 300, "severity": 0.9,
             "access_loss": 0.9, "road_status": "blocked", "hospitals": 1 if i == 1 else 0, "confidence": 0.8, "isolated": True, "lat": 10, "lon": 76} for i in range(1, 5)]


def _res(n_team, n_boat=0, n_amb=0):
    out, i = [], 0
    for kind, n in (("rescue_team", n_team), ("boat", n_boat), ("ambulance", n_amb)):
        for k in range(n):
            i += 1
            out.append({"id": i, "kind": kind, "name": f"{kind} {k}", "status": "available", "lat": 10, "lon": 76 + 0.01 * i, "speed_kmh": 30})
    return out


def test_allocation_covers_each_p1_before_doubling_up_and_explains():
    out = allocate(_cells(), _res(4, 4, 2), lambda r, c: 10.0 + r["id"], "flood")
    by_cell = {}
    for a in out["assignments"]:
        if a["kind"] == "rescue_team":
            by_cell[a["h3_index"]] = by_cell.get(a["h3_index"], 0) + 1
    assert set(by_cell) == {"c1", "c2", "c3", "c4"} and all(v == 1 for v in by_cell.values())
    assert all("P1" in a["reason"] for a in out["assignments"])
    assert out["metrics"]["p1_coverage_pct"] == 100.0


def test_allocation_reports_unserved_when_scarce():
    out = allocate(_cells(), _res(2, 1), lambda r, c: 12.0, "flood")
    m = out["metrics"]
    assert m["p1_served"] < m["p1_total"] and m["unserved_p1_count"] >= 2 and out["unmet"]


def test_scale_roster_whatif():
    base = _res(3)
    out = scale_roster(base, {"rescue_team": 5, "boat": 0}, [{"lat": 10, "lon": 76}])
    assert sum(r["kind"] == "rescue_team" for r in out) == 5 and sum(r["kind"] == "boat" for r in out) == 0


# ---------------------------------------------------------------- escalation / fusion / vulnerability
def test_escalation_diff_and_reasons():
    prev = {"x": {"level": "P2", "score": 0.4, "severity": 0.4, "access_loss": 0.1, "population_exposed": 500, "confidence": 0.7}}
    cur = {"x": {"level": "P1", "score": 0.6, "severity": 0.6, "access_loss": 0.6, "population_exposed": 900, "confidence": 0.7}}
    e = escalation.diff_priorities(prev, cur, {"x": 12})[0]
    assert e["message"] == "CELL 12 ESCALATED FROM P2 TO P1"
    assert {"Hazard severity increased", "Road access decreased", "Population exposure increased"} <= set(e["reasons"])


def test_vulnerability_skips_missing_factors_without_inventing():
    score, meta = vulnerability_score(VulnInput(3000, None, None, None, 5.0, False, 0.5, 0.8, True))
    assert 0 < score < 1 and {"children", "elderly", "housing"} <= set(meta["missing"])


def test_overall_confidence_penalises_missing_and_stale():
    from datetime import datetime, timedelta, timezone
    t = datetime.now(timezone.utc)
    good = [source_status(k, True, 0.9, t, 24, True) for k in ("satellite", "weather", "population", "roads", "infrastructure")]
    stale = [source_status(k, True, 0.9, t - timedelta(days=30), 24, True) for k in ("satellite", "weather", "population", "roads", "infrastructure")]
    missing = good[:2]
    assert overall_confidence(good)[0] > overall_confidence(stale)[0]
    assert overall_confidence(good)[0] > overall_confidence(missing)[0]
