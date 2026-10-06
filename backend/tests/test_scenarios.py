import pytest

from .conftest import login

KEYS = ["kerala_flood_2018", "wayanad_landslide_2024", "urban_flood_synthetic", "wildfire_demo", "cyclone_demo"]


@pytest.mark.parametrize("key", KEYS)
def test_every_scenario_processes_and_is_labelled_demo(client, commander, key):
    r = client.post("/api/events", json={"aoi_method": "demo", "scenario_key": key}, headers=commander)
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["label"] == "DEMONSTRATION DATA" and ev["is_demo"] is True
    assert client.post(f"/api/events/{ev['id']}/process", headers=commander).status_code == 202
    st = client.get(f"/api/events/{ev['id']}/status", headers=commander).json()
    assert st["job"]["status"] == "succeeded", st["job"]
    d = client.get(f"/api/events/{ev['id']}/detections", headers=commander).json()["detections"][0]
    assert d["area_km2"] > 0 and d["hazard"] == ev["hazard"] and d["simulated_input"]
    m = client.get(f"/api/events/{ev['id']}/map", headers=commander).json()
    assert m["label"] == "DEMONSTRATION DATA" and len(m["cells"]["features"]) > 20
    if ev["hazard"] == "wildfire":
        assert d["outputs"]["hotspot_count"] > 0 and d["outputs"]["burn_area_km2"] > 0
    if ev["hazard"] == "cyclone":
        assert {"damage_score", "vegetation_damage", "surge_indicator"} <= set(d["outputs"])
    if ev["hazard"] == "landslide":
        assert d["outputs"]["max_landslide_probability"] > 0.5


def test_new_pass_keeps_history_and_detects_escalation(client, commander):
    eid = client.post("/api/events", json={"aoi_method": "demo", "scenario_key": "kerala_flood_2018"}, headers=commander).json()["id"]
    client.post(f"/api/events/{eid}/process", headers=commander)
    before = client.get(f"/api/events/{eid}/kpis", headers=commander).json()
    nos = {c["h3_index"]: c["cell_no"] for c in client.get(f"/api/events/{eid}/priorities", headers=commander).json()["cells"]}
    assert client.post(f"/api/events/{eid}/new-pass", headers=commander).status_code == 202
    st = client.get(f"/api/events/{eid}/status", headers=commander).json()
    assert st["job"]["status"] == "succeeded"
    after = client.get(f"/api/events/{eid}/kpis", headers=commander).json()
    assert after["assessment_version"] == before["assessment_version"] + 1
    assert after["affected_area_km2"] > before["affected_area_km2"]
    nos2 = {c["h3_index"]: c["cell_no"] for c in client.get(f"/api/events/{eid}/priorities", headers=commander).json()["cells"]}
    assert all(nos2[h] == n for h, n in nos.items() if h in nos2), "cell numbers must stay stable across passes"
    wc = client.get(f"/api/events/{eid}/what-changed", headers=commander).json()
    assert wc["available"] and wc["delta"]["affected_cells"] > 0
    al = client.get(f"/api/events/{eid}/alerts", headers=commander).json()["alerts"]
    assert any(a["trigger"] == "escalation" and "ESCALATED FROM" in a["title"] for a in al)


def test_priority_config_recalculates(client, commander, analysed_event):
    r = client.put(f"/api/events/{analysed_event}/priorities/config", json={"weights": {"severity": 0.7, "exposure": 0.1, "infrastructure": 0.1, "accessibility": 0.1}}, headers=commander)
    assert r.status_code == 200
    assert client.put(f"/api/events/{analysed_event}/priorities/config", json={"thresholds": {"P1": 0.2, "P2": 0.3, "P3": 0.1}}, headers=commander).status_code == 422
    assert client.put(f"/api/events/{analysed_event}/priorities/config", json={"weights": {"bogus": 1}}, headers=commander).status_code == 422
    assert client.put(f"/api/events/{analysed_event}/priorities/config", json={"weights": {}}, headers=login(client, "analyst")).status_code == 403
    client.put(f"/api/events/{analysed_event}/priorities/config", json={"weights": {"severity": 0.35, "exposure": 0.30, "infrastructure": 0.20, "accessibility": 0.15}}, headers=commander)
