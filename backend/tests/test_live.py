"""Real-data (live) mode. Offline tests use fixtures / monkeypatching; the final test hits the real services (set DISHA_LIVE_TESTS=1)."""
import os

import numpy as np
import pytest

from .conftest import login


# ------------------------------------------------------------------ OpenStreetMap parsing
def _way(wid, nodes, coords, **tags):
    return {"type": "way", "id": wid, "nodes": nodes, "geometry": [{"lat": a, "lon": b} for a, b in coords], "tags": {"highway": "secondary", **tags}}


def test_osm_graph_splits_at_intersections_and_keeps_geometry():
    from app.live import osm

    # a long way (nodes 1-2-3-4) crossed at node 3 by a second way (5-3-6); an unrelated island (9-10)
    j = {"elements": [
        _way(1, [1, 2, 3, 4], [(10.00, 76.00), (10.00, 76.01), (10.00, 76.02), (10.00, 76.03)], name="Main Rd"),
        _way(2, [5, 3, 6], [(10.01, 76.02), (10.00, 76.02), (9.99, 76.02)], bridge="yes", highway="tertiary"),
        _way(3, [9, 10], [(11.0, 77.0), (11.0, 77.01)]),
    ]}
    nodes, edges = osm.build_road_graph(j)
    assert len(edges) == 4  # 1..3, 3..4, 5..3, 3..6 ; island dropped (largest component only)
    assert not any(e["name"] == "Unnamed secondary" and e["length_m"] < 2000 and e["geometry"][0][0] > 10.5 for e in edges)
    first = next(e for e in edges if e["name"] == "Main Rd" and len(e["geometry"]) == 3)
    assert first["geometry"][1] == (10.00, 76.01), "intermediate vertex must be preserved as curve geometry"
    assert sum(e["is_bridge"] for e in edges) == 2 and all(e["class"] in ("secondary",) for e in edges)
    assert len(nodes) == 5


def test_osm_features_and_assumed_dependencies():
    from app.live import osm

    j = {"elements": [
        {"type": "node", "id": 1, "lat": 10.0, "lon": 76.0, "tags": {"amenity": "hospital", "name": "Taluk Hospital", "beds": "120"}},
        {"type": "node", "id": 2, "lat": 10.01, "lon": 76.0, "tags": {"power": "substation", "name": "Sub A"}},
        {"type": "way", "id": 3, "center": {"lat": 10.0, "lon": 76.01}, "tags": {"amenity": "school", "name": "GHS"}},
        {"type": "node", "id": 4, "lat": 10.0, "lon": 76.02, "tags": {"place": "village", "name": "Koratty"}},
    ]}
    p = osm.parse_features(j)
    kinds = {f["kind"] for f in p["facilities"]}
    assert {"hospital", "power", "school"} <= kinds
    hosp = next(f for f in p["facilities"] if f["kind"] == "hospital")
    assert hosp["capacity"] == 120 and hosp["depends_on"] == ["Sub A"]  # assumed dependency on nearest substation
    assert p["places"][0]["name"] == "Koratty"
    assert any(s["capacity_assumed"] for s in p["shelters"])  # school as shelter: capacity assumed


# ------------------------------------------------------------------ population disaggregation
def test_dasymetric_population_conserves_totals():
    from app.live.population import disaggregate

    parent = np.array([[0, 0, 1, 1], [0, 0, 1, 1]])
    total = np.where(parent == 0, 1000.0, 400.0)
    weights = np.array([[1, 1, 0, 0.04], [0, 0, 1, 0.04]], dtype=float)
    out = disaggregate(total, parent, weights)
    assert out[parent == 0].sum() == pytest.approx(1000.0, rel=1e-4)
    assert out[parent == 1].sum() == pytest.approx(400.0, rel=1e-4)
    assert out[0, 0] > out[1, 0] and out[1, 2] > out[0, 3], "people go where the built-up weight is"


# ------------------------------------------------------------------ road geometry
def test_curved_road_is_classified_along_its_real_shape():
    from app.engines.geo import GridTransform
    from app.engines.roads import classify_segments

    t = GridTransform(76.0, 10.0, 76.02, 10.02, 100, 100)
    mask = np.zeros((100, 100), bool)
    mask[20:40, 40:60] = True  # flooded patch in the north-middle
    # straight chord between the ends would miss the patch; the real polyline passes through it
    lon_mid, lat_mid = t.rc_to_lonlat(30, 50)
    geom = [(10.0005, 76.0005), (float(lat_mid), float(lon_mid)), (10.0005, 76.0195)]
    nodes = {0: geom[0], 1: geom[2]}
    seg = classify_segments([{"u": 0, "v": 1, "class": "local", "is_bridge": False, "length_m": 4500.0, "name": "Curved Rd", "geometry": geom}], nodes, t, mask, None, 8)[0]
    chord = classify_segments([{"u": 0, "v": 1, "class": "local", "is_bridge": False, "length_m": 4500.0, "name": "Chord", "geometry": [geom[0], geom[2]]}], nodes, t, mask, None, 8)[0]
    assert seg["flooded_fraction"] > chord["flooded_fraction"]
    assert len(seg["coords"]) == 3 and seg["coords"][1][0] == pytest.approx(lon_mid, abs=1e-5)


# ------------------------------------------------------------------ Sentinel-1 pairing rules
def test_s1_pair_requires_same_track_and_direction(monkeypatch):
    from app.live import imagery
    from app.live.net import LiveDataError

    def item(date, orbit, direction):
        return {"id": f"S1_{date}_{orbit}", "geometry": {"type": "Polygon", "coordinates": [[[75, 9], [78, 9], [78, 12], [75, 12], [75, 9]]]},
                "properties": {"datetime": f"{date}T00:40:00Z", "sat:relative_orbit": orbit, "sat:orbit_state": direction}}

    bbox = (76.2, 10.2, 76.3, 10.3)
    pre, post = [item("2018-08-09", 165, "descending"), item("2018-07-28", 99, "ascending")], [item("2018-08-21", 165, "descending"), item("2018-08-21", 99, "ascending")]
    monkeypatch.setattr(imagery, "stac_search", lambda c, b, d=None, query=None, limit=50: pre if d.endswith("2018-08-12") else post)
    a, b = imagery.pick_s1_pair(bbox, "2018-08-12", "2018-08-17", "2018-08-26")
    assert a["properties"]["sat:relative_orbit"] == b["properties"]["sat:relative_orbit"] and a["id"].startswith("S1_2018-08-09")  # closest-in-time pair on the same track
    monkeypatch.setattr(imagery, "stac_search", lambda c, b, d=None, query=None, limit=50: [item("2018-08-09", 165, "descending")] if d.endswith("2018-08-12") else [item("2018-08-21", 99, "ascending")])
    with pytest.raises(LiveDataError):
        imagery.pick_s1_pair(bbox, "2018-08-12", "2018-08-17", "2018-08-26")


# ------------------------------------------------------------------ event creation rules
def test_real_event_validation_and_labelling(client, commander):
    ok = client.post("/api/events", json={"aoi_method": "demo", "scenario_key": "kerala_kuttanad_2018"}, headers=commander)
    assert ok.status_code == 201
    ev = ok.json()
    assert ev["is_demo"] is False and ev["label"] == "REAL DATA" and ev["data_mode"] == "live"
    bad_dates = client.post("/api/events", json={"hazard": "flood", "aoi_method": "coordinates", "aoi": {"west": 76.2, "south": 10.2, "east": 76.3, "north": 10.3},
                                                 "data_mode": "live", "live": {"pre_end": "2018-08-20", "post_start": "2018-08-10", "post_end": "2018-08-30"}}, headers=commander)
    assert bad_dates.status_code == 422 and "pre_end < post_start" in bad_dates.text
    missing = client.post("/api/events", json={"hazard": "flood", "aoi_method": "coordinates", "aoi": {"west": 76.2, "south": 10.2, "east": 76.3, "north": 10.3}, "data_mode": "live"}, headers=commander)
    assert missing.status_code == 422
    big = client.post("/api/events", json={"hazard": "flood", "aoi_method": "coordinates", "aoi": {"west": 76.0, "south": 10.0, "east": 76.6, "north": 10.6},
                                           "data_mode": "live", "live": {"pre_end": "2018-08-01", "post_start": "2018-08-17", "post_end": "2018-08-30"}}, headers=commander)
    assert big.status_code == 422 and "too large" in big.text
    # new-pass is a simulation feature; refused for real events
    done = client.post(f"/api/events/{ev['id']}/new-pass", headers=commander)
    assert done.status_code in (409,)


# ------------------------------------------------------------------ pipeline live branch (network mocked)
def _fake_real_world(*a, **k):
    from datetime import datetime, timezone

    from app.demo.world import build_world
    from app.demo.scenarios import SCENARIOS, scenario_bounds

    s = SCENARIOS["kerala_flood_2018"]
    w = build_world("flood", scenario_bounds("kerala_kuttanad_2018"), seed=s["seed"], params=s["params"], variant=s["variant"])  # same bounds as the event AOI
    now = datetime.now(timezone.utc)
    w.is_real, w.demographics_available, w.optical_available = True, False, False
    w.passes = [{"sensor": "sentinel-1", "phase": "pre", "acquired_at": datetime(2018, 8, 9, tzinfo=timezone.utc), "cloud_cover_pct": None, "orbit": "descending rel. orbit 165", "polarisation": "VV", "source": "test fixture"},
                {"sensor": "sentinel-1", "phase": "post", "acquired_at": datetime(2018, 8, 21, tzinfo=timezone.utc), "cloud_cover_pct": None, "orbit": "descending rel. orbit 165", "polarisation": "VV", "source": "test fixture"}]
    w.provenance = {k: {"name": f"{k} (fixture)", "provider": "fixture", "quality": 0.8, "last_updated": now, "stale_after_hours": 24 * 365 * 5} for k in ("satellite", "dem", "weather", "population", "roads", "infrastructure")}
    w.resources_note = "hypothetical roster"
    for f in w.facilities:
        f["osm_id"] = "node/1"
    return w


def test_live_branch_runs_without_demographics_and_labels_sources(client, commander, monkeypatch):
    monkeypatch.setattr("app.live.real_world.build_live_world", _fake_real_world)
    eid = client.post("/api/events", json={"aoi_method": "demo", "scenario_key": "kerala_kuttanad_2018"}, headers=commander).json()["id"]
    assert client.post(f"/api/events/{eid}/process", headers=commander).status_code == 202
    st = client.get(f"/api/events/{eid}/status", headers=commander).json()
    assert st["job"]["status"] == "succeeded", st["job"]
    assert "Sentinel-1 SAR is the sole detection source" in client.get(f"/api/events/{eid}/detections", headers=commander).json()["detections"][0]["sensor_explanation"]
    d = client.get(f"/api/events/{eid}/detections", headers=commander).json()
    assert d["detections"][0]["simulated_input"] is False and all(p["simulated"] is False for p in d["passes"])
    top = client.get(f"/api/events/{eid}/priorities?level=P1,P2", headers=commander).json()["cells"][0]["h3_index"]
    cell = client.get(f"/api/events/{eid}/cells/{top}", headers=commander).json()
    assert cell["population"]["vulnerable"] == 0 and {"children", "elderly", "housing"} <= set(cell["vulnerability"]["missing"]), "unavailable demographics must be skipped, not invented"
    assert cell["population"]["note"] and "Not a census" in cell["population"]["note"] or "estimate" in cell["population"]["note"].lower()
    health = client.get(f"/api/events/{eid}/data-health", headers=commander).json()
    assert health["simulated"] is True  # the hypothetical resources roster is still flagged as simulated
    srcs = client.get("/api/admin/data-sources", headers=login(client, "admin")).json()
    mine = {s["key"]: s for s in srcs if s["event_id"] == eid}
    assert mine["roads"]["simulated"] is False and mine["resources"]["simulated"] is True
    pdf = client.get(f"/api/events/{eid}/report", headers=commander)
    assert pdf.status_code == 200 and b"DEMONSTRATION" not in pdf.content[:3000]
    gj = client.get(f"/api/events/{eid}/export?format=geojson", headers=commander).json()
    assert "SIMULATED" in " ".join(gj["metadata"]["data_sources"])  # only the hypothetical roster


# ------------------------------------------------------------------ real services (opt-in)
@pytest.mark.skipif(not os.environ.get("DISHA_LIVE_TESTS"), reason="set DISHA_LIVE_TESTS=1 to hit Planetary Computer / Overpass / Open-Meteo")
def test_real_kuttanad_end_to_end(client, commander):
    eid = client.post("/api/events", json={"aoi_method": "demo", "scenario_key": "kerala_kuttanad_2018"}, headers=commander).json()["id"]
    client.post(f"/api/events/{eid}/process", headers=commander)
    st = client.get(f"/api/events/{eid}/status", headers=commander).json()
    assert st["job"]["status"] == "succeeded", st["job"]
    det = client.get(f"/api/events/{eid}/detections", headers=commander).json()
    d = det["detections"][0]
    assert d["simulated_input"] is False and d["area_km2"] > 1.0
    s1 = [p for p in det["passes"] if p["sensor"] == "sentinel-1"]
    assert {p["phase"] for p in s1} == {"pre", "post"} and not any(p["simulated"] for p in s1)
    assert any("Planetary Computer" in p["source"] for p in s1)
    k = client.get(f"/api/events/{eid}/kpis", headers=commander).json()
    assert k["roads"]["total"] > 500 and k["critical_infrastructure"]["total"] > 20
